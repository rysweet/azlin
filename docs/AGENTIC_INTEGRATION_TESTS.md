# Agentic "Do It" Mode - Integration Tests

**Feature:** `azlin do` natural language command execution
**Issue:** #154
**Status:** ✅ All Test Cases Defined

This document outlines comprehensive integration tests for the agentic "do it" mode. These tests cover a wide range of natural language commands to verify end-to-end functionality.

---

## Test Setup

### Prerequisites
```bash
# Set API key
export ANTHROPIC_API_KEY=your-key-here

# Ensure Azure authentication
az login

# Configure resource group
azlin config set resource_group=your-rg
```

### Test Environment
- Azure subscription with VM quota
- Anthropic API access
- Test VMs can be provisioned and deleted
- Cost tracking enabled

---

## Category 1: VM Provisioning (5 tests)

### Test 1.1: Simple VM Creation
**Command:**
```bash
azlin do "create a new vm called Sam"
```

**Expected Behavior:**
- Parses intent as `provision_vm`
- Extracts VM name: "Sam"
- Generates command: `azlin new --name Sam`
- Provisions VM with default settings
- Returns success with IP address

### Test 1.2: VM with Repository
**Command:**
```bash
azlin do "provision a vm named DevBox with my dotfiles repo"
```

**Expected Behavior:**
- Recognizes repository requirement
- May prompt for repository URL
- Provisions VM with Git repository cloned
- Validates VM is accessible

### Test 1.3: Multiple VMs
**Command:**
```bash
azlin do "create 3 vms for testing"
```

**Expected Behavior:**
- Recognizes count=3
- May confirm resource creation
- Provisions 3 VMs with generated names
- Reports all VM IPs

### Test 1.4: GPU VM
**Command:**
```bash
azlin do "provision a vm with GPU support for machine learning"
```

**Expected Behavior:**
- Recognizes GPU requirement
- Selects appropriate VM size (NC series)
- May warn about cost
- Provisions GPU-enabled VM

### Test 1.5: VM with Storage
**Command:**
```bash
azlin do "create a vm called DataNode and mount 100GB shared storage"
```

**Expected Behavior:**
- Provisions VM
- Creates or uses existing NFS storage
- Mounts storage on VM
- Validates mount successful

---

## Category 2: VM Management (6 tests)

### Test 2.1: List VMs
**Command:**
```bash
azlin do "show me all my vms"
```

**Expected Behavior:**
- Generates: `azlin list`
- Displays VM names, statuses, IPs
- Formats output clearly

### Test 2.2: VM Status Check
**Command:**
```bash
azlin do "what's the status of vm Sam"
```

**Expected Behavior:**
- Generates: `azlin status --vm Sam`
- Shows power state, IP, region
- Reports if VM not found

### Test 2.3: Start VM
**Command:**
```bash
azlin do "start the vm named Sam"
```

**Expected Behavior:**
- Generates: `azlin start Sam`
- Starts VM if stopped
- Waits for IP assignment
- Reports when ready

### Test 2.4: Stop VM
**Command:**
```bash
azlin do "stop all my test vms"
```

**Expected Behavior:**
- Lists VMs matching "test" pattern
- Confirms action
- Stops multiple VMs in parallel
- Reports success for each

### Test 2.5: Delete VM
**Command:**
```bash
azlin do "delete the vm called Sam"
```

**Expected Behavior:**
- Generates: `azlin kill Sam`
- Confirms deletion (unless --force)
- Deletes VM and resources
- Reports resources deleted

### Test 2.6: Update VM
**Command:**
```bash
azlin do "update all my vms"
```

**Expected Behavior:**
- Generates: `azlin update` for each VM
- Updates development tools
- Reports update status

---

## Category 3: File Operations (4 tests)

### Test 3.1: Sync to VM
**Command:**
```bash
azlin do "sync my home directory to vm Sam"
```

**Expected Behavior:**
- Generates: `azlin sync --vm-name Sam`
- Syncs ~/.azlin/home/ to VM
- Shows files transferred
- Reports completion

### Test 3.2: Sync All VMs
**Command:**
```bash
azlin do "sync all my vms"
```

**Expected Behavior:**
- Lists all running VMs
- Confirms action
- Syncs to each VM
- Reports success/failures

### Test 3.3: Copy File to VM
**Command:**
```bash
azlin do "copy myfile.txt to vm Sam"
```

**Expected Behavior:**
- Generates: `azlin cp myfile.txt Sam:~/myfile.txt`
- Transfers file via SCP
- Validates transfer
- Shows destination path

### Test 3.4: Copy from VM
**Command:**
```bash
azlin do "get results.csv from vm DataNode"
```

**Expected Behavior:**
- Generates: `azlin cp DataNode:~/results.csv ./results.csv`
- Downloads file
- Shows local path

---

## Category 4: Cost Management (3 tests)

### Test 4.1: Current Cost
**Command:**
```bash
azlin do "what's my current azure cost"
```

**Expected Behavior:**
- Generates: `azlin cost`
- Shows running/stopped VMs
- Calculates estimated cost
- Breaks down by resource

### Test 4.2: Cost Over Period
**Command:**
```bash
azlin do "show me the cost over the last week"
```

**Expected Behavior:**
- Generates: `azlin cost --from "7 days ago"`
- Retrieves actual Azure costs
- Shows daily breakdown
- Calculates total

### Test 4.3: Cost by VM
**Command:**
```bash
azlin do "how much is vm Sam costing me"
```

**Expected Behavior:**
- Generates: `azlin cost --by-vm`
- Filters for Sam
- Shows compute + storage costs
- Provides monthly estimate

---

## Category 5: Storage Operations (3 tests)

### Test 5.1: Create Storage
**Command:**
```bash
azlin do "create 200GB shared storage called project-data"
```

**Expected Behavior:**
- Generates: `azlin storage create project-data --size 200`
- Creates NFS storage account
- Shows mount endpoint
- Reports success

### Test 5.2: List Storage
**Command:**
```bash
azlin do "show all my storage accounts"
```

**Expected Behavior:**
- Generates: `azlin storage list`
- Lists storage accounts
- Shows capacity, tier, region
- Displays mount endpoints

### Test 5.3: Storage Status
**Command:**
```bash
azlin do "how much space is left on project-data storage"
```

**Expected Behavior:**
- Generates: `azlin storage status project-data`
- Shows used/available capacity
- Lists connected VMs
- Reports usage percentage

---

## Category 6: Complex Multi-Step (4 tests)

### Test 6.1: Full Development Setup
**Command:**
```bash
azlin do "set up a new development environment called DevEnv"
```

**Expected Behavior:**
- Provisions VM
- Mounts default storage
- Syncs home directory
- Installs development tools
- Reports completion with SSH command

### Test 6.2: Test Fleet Provisioning
**Command:**
```bash
azlin do "create 5 test vms and sync them all"
```

**Expected Behavior:**
- Plans multi-step execution
- Provisions 5 VMs
- Waits for all to be ready
- Syncs home to all 5
- Reports all IPs

### Test 6.3: Cost Optimization
**Command:**
```bash
azlin do "show me my costs and stop any vms I'm not using"
```

**Expected Behavior:**
- Gets cost report
- Identifies stopped VMs still costing money
- May identify idle running VMs
- Proposes optimizations
- Asks for confirmation

### Test 6.4: Cleanup Old Resources
**Command:**
```bash
azlin do "delete all vms older than 30 days"
```

**Expected Behavior:**
- Lists all VMs
- Filters by creation date
- Shows VMs to delete
- Confirms action
- Deletes selected VMs
- Reports resources freed

---

## Category 7: Monitoring & Diagnostics (3 tests)

### Test 7.1: VM Health Check
**Command:**
```bash
azlin do "check if all my vms are healthy"
```

**Expected Behavior:**
- Gets status of all VMs
- Checks connectivity (SSH)
- Verifies NFS mounts
- Reports issues found
- Suggests remediation

### Test 7.2: Resource Usage
**Command:**
```bash
azlin do "show me cpu and memory usage across my vms"
```

**Expected Behavior:**
- Generates: `azlin w` or `azlin top`
- Collects metrics from all VMs
- Shows resource utilization
- Identifies overloaded VMs

### Test 7.3: View Logs
**Command:**
```bash
azlin do "show me the logs from vm Sam"
```

**Expected Behavior:**
- Generates: `azlin logs Sam`
- Retrieves cloud-init logs
- Shows system logs
- Highlights errors

---

## Category 8: Ambiguous Requests (4 tests)

### Test 8.1: Low Confidence - Ask for Clarification
**Command:**
```bash
azlin do "do something with Sam"
```

**Expected Behavior:**
- Low confidence score (< 0.7)
- Warns user about ambiguity
- Asks for confirmation
- May suggest alternatives

### Test 8.2: Multiple Interpretations
**Command:**
```bash
azlin do "update Sam"
```

**Expected Behavior:**
- Could mean: update tools, update OS, or edit config
- Shows multiple interpretations
- Asks user to choose
- Executes selected option

### Test 8.3: Invalid Request
**Command:**
```bash
azlin do "make me coffee"
```

**Expected Behavior:**
- Recognizes request is outside azlin scope
- Returns friendly error
- May suggest valid alternatives
- Does not execute anything

### Test 8.4: Dangerous Operation Without Confirmation
**Command:**
```bash
azlin do "delete everything"
```

**Expected Behavior:**
- High-risk operation detected
- Requires explicit confirmation
- Shows what will be deleted
- Allows cancellation
- Only proceeds if user confirms

---

## Test Execution

### Manual Testing
Run each test category sequentially:

```bash
# Category 1: VM Provisioning
azlin do "create a new vm called Sam" --verbose

# Category 2: VM Management
azlin do "show me all my vms" --verbose

# Category 3: File Operations
azlin do "sync my home directory to vm Sam" --verbose

# ... etc for all categories
```

### Automated Testing (Future)
Create pytest integration tests that:
1. Mock Claude API responses
2. Verify intent parsing correctness
3. Validate command generation
4. Test error handling

### Dry Run Testing
Test intent parsing without execution:

```bash
# Test all commands in dry-run mode
for cmd in "${NATURAL_LANGUAGE_COMMANDS[@]}"; do
    azlin do "$cmd" --dry-run --verbose
done
```

---

## Expected Test Results

### Success Criteria
- ✅ All basic commands parse correctly (confidence > 0.9)
- ✅ Complex multi-step commands generate valid plans
- ✅ Ambiguous commands trigger clarification
- ✅ Dangerous operations require confirmation
- ✅ Error handling prevents system damage
- ✅ Execution results validated correctly

### Performance Benchmarks
- Intent parsing: < 2 seconds
- Command execution: Varies by command
- Result validation: < 1 second
- End-to-end: < 5 minutes for complex operations

### Error Handling
- API key missing: Clear error message
- Azure auth failure: Redirect to `az login`
- Low confidence: Ask for clarification
- Command failure: Show error + suggest fix
- Timeout: Cancel gracefully

---

## Test Coverage Summary

| Category | Test Count | Status |
|----------|------------|--------|
| VM Provisioning | 5 | ⏳ Pending |
| VM Management | 6 | ⏳ Pending |
| File Operations | 4 | ⏳ Pending |
| Cost Management | 3 | ⏳ Pending |
| Storage Operations | 3 | ⏳ Pending |
| Complex Multi-Step | 4 | ⏳ Pending |
| Monitoring & Diagnostics | 3 | ⏳ Pending |
| Ambiguous Requests | 4 | ⏳ Pending |
| **TOTAL** | **32** | **Ready for Testing** |

---

## Next Steps

1. ✅ Define comprehensive test cases (this document)
2. ⏳ Set up test environment with API keys
3. ⏳ Run manual tests for each category
4. ⏳ Document results and issues
5. ⏳ Create automated integration tests
6. ⏳ Add tests to CI/CD pipeline

---

## Notes

- Tests require live Azure subscription (costs may apply)
- Anthropic API calls will consume tokens
- Some tests are destructive (delete VMs)
- Always use test resource group
- Monitor costs during testing

**Remember:** The goal is to validate that natural language commands work end-to-end, from parsing → execution → validation, with a wide variety of real-world use cases.

---

🤖 Generated with [Claude Code](https://claude.com/claude-code)

**Branch:** feat/issue-154-agentic-do-mode
**Issue:** #154
