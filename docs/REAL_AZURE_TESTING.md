# Real Azure Integration Testing for Agentic "azlin do"

**Status:** ⏳ Ready for Manual Testing
**Created:** 2025-10-21
**PR:** #156
**Branch:** feat/issue-154-agentic-do-mode

---

## Executive Summary

The agentic "azlin do" command **has NOT been tested against real Azure resources yet**. This document provides:
1. Why real testing is essential
2. What has been tested (unit tests only)
3. Step-by-step manual testing procedure
4. Automated test script usage
5. Expected results and known risks

---

## Why Real Testing is Essential

### Current Test Coverage
✅ **Unit Tests (83 passing)**
- IntentParser logic
- CommandExecutor subprocess handling
- ResultValidator error handling
- ObjectiveManager state persistence
- AuditLogger security features

❌ **NOT Tested**
- Claude API intent parsing with real requests
- Actual Azure resource creation via natural language
- End-to-end flow from NL → Azure CLI → validation
- Error handling with real Azure failures
- Multi-step operations with real timing
- Cost estimation accuracy
- User confirmation flows

### Risk Assessment

**High Risk:**
- Natural language → command translation errors could create/delete wrong resources
- Ambiguous requests might execute unintended operations
- API rate limiting or timeouts not tested
- Cost estimation could be wildly inaccurate

**Medium Risk:**
- User confirmation bypasses not tested
- Concurrent operation handling
- Large-scale operations (10+ VMs)

**Low Risk:**
- Basic list/status commands (read-only)
- Dry-run mode execution

---

## Prerequisites

### 1. ANTHROPIC_API_KEY
```bash
# Get your API key from: https://console.anthropic.com/
export ANTHROPIC_API_KEY=sk-ant-xxxxx...
```

### 2. Azure Authentication
```bash
# Ensure you're logged in
az login
az account show

# Set default subscription if needed
az account set --subscription "your-subscription-id"
```

### 3. azlin Configuration
```bash
# Set default resource group
azlin config set default_resource_group=azlin-test-rg

# Or specify with --rg flag in each command
```

### 4. Install from Branch
```bash
cd /Users/ryan/src/azlin-azdoit
uv pip install -e .

# Verify installation
python -m azlin.cli do --help
```

---

## Manual Testing Procedure

### Phase 1: Dry-Run Tests (Safe, No Azure Changes)

These tests only call the Claude API to parse intent - they don't execute commands.

#### Test 1.1: Simple List Command
```bash
python -m azlin.cli do "list all my vms" --dry-run --verbose
```

**Expected Output:**
- Parsed intent: `list_vms`
- Generated command: `azlin list`
- No actual execution
- Confidence score > 0.9

#### Test 1.2: VM Creation (Dry-Run)
```bash
python -m azlin.cli do "create a new vm called test-agentic-001" --dry-run --verbose
```

**Expected Output:**
- Parsed intent: `provision_vm`
- Parameters: `vm_name = test-agentic-001`
- Generated command: `azlin new --name test-agentic-001`
- No actual provisioning

#### Test 1.3: Complex Multi-Step
```bash
python -m azlin.cli do "provision 3 vms and sync them all" --dry-run --verbose
```

**Expected Output:**
- Parsed intent: `provision_vm` + `sync_vms`
- Multiple commands planned
- Shows execution plan
- Asks for confirmation (even in dry-run)

#### Test 1.4: Ambiguous Request
```bash
python -m azlin.cli do "do something with Sam" --dry-run --verbose
```

**Expected Output:**
- Low confidence score (< 0.7)
- Warning about ambiguity
- May ask for clarification
- Should NOT execute anything

#### Test 1.5: Invalid Request
```bash
python -m azlin.cli do "make me coffee" --dry-run --verbose
```

**Expected Output:**
- Recognizes out-of-scope request
- Friendly error message
- No command generation
- Suggests valid alternatives

---

### Phase 2: Read-Only Real Tests (Safe)

These tests query Azure but don't create/modify/delete resources.

#### Test 2.1: List VMs
```bash
python -m azlin.cli do "show me all my vms" --verbose
```

**Expected Output:**
- Executes: `azlin list`
- Shows actual VMs in resource group
- Returns success
- Result validation confirms list displayed

#### Test 2.2: VM Status
```bash
python -m azlin.cli do "what is the status of my vms" --verbose
```

**Expected Output:**
- Executes: `azlin status`
- Shows power states, IPs, regions
- Returns success
- Validates status information retrieved

#### Test 2.3: Cost Query
```bash
python -m azlin.cli do "what are my azure costs" --verbose
```

**Expected Output:**
- Executes: `azlin cost`
- Shows running costs
- Estimates monthly spend
- Returns success

---

### Phase 3: Write Operations (Costs Money - Use with Caution)

⚠️ **WARNING**: These tests will CREATE real Azure resources and incur costs!

#### Test 3.1: Create Single VM
```bash
python -m azlin.cli do "create a new vm called agentic-test-001" --verbose
```

**Expected Behavior:**
1. Parses intent correctly
2. Shows command to execute
3. **Asks for user confirmation**
4. Provisions VM with default settings
5. Waits for IP assignment
6. Validates VM created successfully
7. Returns VM details (name, IP, region)

**Cost:** ~$0.10/hour for Standard_B2s

**Manual Verification:**
```bash
# Check VM exists
azlin list

# Check actual Azure resource
az vm show --resource-group <rg> --name agentic-test-001
```

#### Test 3.2: File Sync
```bash
# Assumes agentic-test-001 from 3.1 exists
python -m azlin.cli do "sync my home directory to vm agentic-test-001" --verbose
```

**Expected Behavior:**
1. Parses intent as `sync_vms`
2. Shows: `azlin sync --vm-name agentic-test-001`
3. Syncs ~/.azlin/home/ to VM
4. Shows files transferred
5. Validates sync completed

#### Test 3.3: VM Lifecycle
```bash
# Stop VM
python -m azlin.cli do "stop vm agentic-test-001" --verbose

# Verify stopped
azlin status

# Start VM
python -m azlin.cli do "start vm agentic-test-001" --verbose

# Verify running
azlin status
```

#### Test 3.4: Cleanup
```bash
python -m azlin.cli do "delete vm agentic-test-001" --verbose
```

**Expected Behavior:**
1. Parses as `delete_vm`
2. **MUST ask for confirmation** (destructive operation)
3. Shows what will be deleted
4. Allows cancellation
5. If confirmed, deletes VM and resources
6. Validates deletion successful

**Manual Verification:**
```bash
# VM should be gone
azlin list

# Azure resources cleaned up
az vm show --resource-group <rg> --name agentic-test-001
# Should return: ResourceNotFound
```

---

### Phase 4: Edge Cases and Error Handling

#### Test 4.1: Quota Exceeded
```bash
# Request more resources than quota allows
python -m azlin.cli do "create 100 vms" --verbose
```

**Expected Behavior:**
- Should detect high resource count
- Warn about cost and quota
- If executed, handle quota error gracefully
- Suggest alternatives (different region, smaller count)

#### Test 4.2: Network Failure
```bash
# Disconnect network during execution (manually)
python -m azlin.cli do "create vm test" --verbose
# (disconnect WiFi)
```

**Expected Behavior:**
- Timeout handling
- Graceful error message
- No orphaned resources
- State saved for recovery

#### Test 4.3: Invalid VM Name
```bash
python -m azlin.cli do "create a vm called INVALID@NAME!" --verbose
```

**Expected Behavior:**
- Validation error from Azure CLI
- Clear error message to user
- No resources created
- Suggests valid naming pattern

---

## Automated Test Script

We've created an automated test script that runs all the above tests systematically.

### Usage

```bash
cd /Users/ryan/src/azlin-azdoit

# Set API key
export ANTHROPIC_API_KEY=your-key-here

# Run all tests (including VM creation)
./scripts/test_agentic_integration.sh

# Skip VM creation tests (safer, no costs)
SKIP_VM_CREATION=1 ./scripts/test_agentic_integration.sh
```

### Test Coverage

The script runs:
- 3 dry-run tests (safe)
- 4 read-only tests (safe)
- 3 VM creation tests (costs money, optional)
- 2 error handling tests

**Total: 12 tests**

### Example Output

```
[INFO] Starting azlin agentic integration tests...
[INFO] Running pre-flight checks...
[INFO] ✓ ANTHROPIC_API_KEY is set
[INFO] ✓ Azure CLI authenticated
[INFO] ✓ azlin available
[INFO] All pre-flight checks passed!

[INFO] ===== DRY-RUN TESTS =====
[INFO] Running test: Dry-run: List VMs
[INFO] ✅ PASSED: Dry-run: List VMs
[INFO] Running test: Dry-run: Create VM
[INFO] ✅ PASSED: Dry-run: Create VM

...

========================================
INTEGRATION TEST SUMMARY
========================================
Total tests passed: 12
Total tests failed: 0

[INFO] 🎉 ALL TESTS PASSED!
========================================
```

---

## Success Criteria

### Minimum Viable Testing (Before Merge)

✅ **Required:**
1. All dry-run tests pass
2. Read-only tests pass (list, status, cost)
3. At least 1 full VM lifecycle test (create → verify → delete)
4. Error handling test passes (invalid request)
5. No unexpected Azure resources created
6. No credential leaks or security issues

⏳ **Recommended:**
1. Multi-step operation test
2. File sync test
3. Ambiguous request handling
4. Cost estimation accuracy validation

❌ **Optional (Post-Merge):**
1. Large-scale testing (10+ VMs)
2. Concurrent operation testing
3. Failure recovery testing
4. Performance benchmarking

---

## Known Limitations

### Current Implementation

1. **Phase 1 Only**: azdoit advanced features not yet implemented
   - No strategy selection (Azure CLI, Terraform, MCP)
   - No cost estimation (uses placeholder)
   - No failure recovery
   - No research mode

2. **Natural Language Parsing**: Accuracy depends on Claude API
   - May misinterpret ambiguous requests
   - Confidence threshold not tuned yet
   - No context memory between commands

3. **Error Handling**: Basic implementation
   - Some Azure error messages not parsed
   - Timeout handling not comprehensive
   - No partial rollback on multi-step failures

### Safety Features Implemented

✅ User confirmation for destructive operations
✅ Dry-run mode
✅ API key validation
✅ Azure auth check
✅ Command validation before execution
✅ Execution history tracking
✅ Audit logging

---

## Testing Checklist

Before declaring "azlin do" production-ready:

### Functional Testing
- [ ] All dry-run tests pass
- [ ] Read-only operations work (list, status, cost)
- [ ] Single VM creation works end-to-end
- [ ] VM deletion with confirmation works
- [ ] File sync works
- [ ] Multi-step operations work
- [ ] Ambiguous request handling works
- [ ] Invalid request handling works

### Security Testing
- [ ] API key not logged or exposed
- [ ] User confirmation enforced for destructive ops
- [ ] No command injection vulnerabilities
- [ ] Audit log captures all operations
- [ ] Failed operations logged

### Error Handling
- [ ] Quota exceeded handled gracefully
- [ ] Network failures don't leave orphaned resources
- [ ] Invalid parameters caught before execution
- [ ] Timeout handling works
- [ ] Azure errors translated to user-friendly messages

### Performance
- [ ] Intent parsing < 2 seconds
- [ ] Command execution matches native azlin
- [ ] Result validation < 1 second
- [ ] No unnecessary API calls

### Cost Management
- [ ] Cost warnings shown for expensive operations
- [ ] Actual costs match estimates
- [ ] No surprise charges from failed operations

---

## Manual Testing Log Template

Copy this template for each testing session:

```markdown
## Testing Session

**Date:** YYYY-MM-DD
**Tester:** [Your Name]
**Branch:** feat/issue-154-agentic-do-mode
**Commit:** [git rev-parse HEAD]
**Environment:**
- Azure Subscription: [subscription-id]
- Resource Group: [rg-name]
- Region: [region]

### Pre-Flight Checks
- [ ] ANTHROPIC_API_KEY set
- [ ] Azure authenticated
- [ ] azlin configured
- [ ] Branch installed

### Test Results

#### Dry-Run Tests
- [ ] PASS/FAIL: List VMs
- [ ] PASS/FAIL: Create VM
- [ ] PASS/FAIL: Multi-step
- [ ] PASS/FAIL: Ambiguous request
- [ ] PASS/FAIL: Invalid request

#### Read-Only Tests
- [ ] PASS/FAIL: List VMs
- [ ] PASS/FAIL: VM status
- [ ] PASS/FAIL: Cost query

#### Write Operations (Optional)
- [ ] PASS/FAIL/SKIP: Create VM
- [ ] PASS/FAIL/SKIP: Sync files
- [ ] PASS/FAIL/SKIP: Delete VM

### Issues Found
[List any bugs, unexpected behavior, or concerns]

### Resources Created
[List any Azure resources that were created during testing]

### Cleanup Status
[Confirm all test resources deleted]

### Recommendation
- [ ] Ready to merge
- [ ] Needs fixes before merge
- [ ] Requires additional testing

### Notes
[Any additional observations or recommendations]
```

---

## Next Steps

### For Developers

1. **Run Automated Script:**
   ```bash
   export ANTHROPIC_API_KEY=your-key-here
   SKIP_VM_CREATION=1 ./scripts/test_agentic_integration.sh
   ```

2. **Manual Verification:**
   - Test 1 complete lifecycle manually
   - Document results in testing log
   - File any bugs found

3. **Update PR:**
   - Add testing results to PR description
   - Mark integration tests as ✅ or ⏳
   - Note any known issues

### For Reviewers

1. **Review Test Plan:** Does it cover critical scenarios?
2. **Check Test Results:** Were all required tests run?
3. **Verify Safety:** Are destructive operations properly gated?
4. **Assess Risk:** Is it safe to merge given test coverage?

### For Users (Post-Merge)

1. Start with dry-run mode
2. Test non-destructive operations first
3. Monitor costs closely
4. Report any issues immediately

---

## Support

If you encounter issues during testing:

1. **Check logs:**
   - Test script log: `/tmp/azlin-agentic-test-*.log`
   - Audit log: `~/.azlin/audit.log`
   - Claude API responses: Enable `--verbose`

2. **Common issues:**
   - "API key not set": `export ANTHROPIC_API_KEY=...`
   - "Not authenticated": `az login`
   - "No resource group": `azlin config set default_resource_group=...`
   - "Command not found": Reinstall with `uv pip install -e .`

3. **Report bugs:**
   - GitHub Issue: #156
   - Include: command, error message, logs
   - Expected vs actual behavior

---

## Conclusion

The agentic "azlin do" command requires real Azure integration testing before being considered production-ready. This document provides:

- ✅ Comprehensive test plan
- ✅ Automated test script
- ✅ Safety guidelines
- ✅ Success criteria
- ✅ Documentation template

**Next Action:** Run the automated test script with your ANTHROPIC_API_KEY and document results.

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Status:** Ready for testing
**Recommendation:** Test before merging to ensure quality
