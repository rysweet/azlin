# Manual Test Plan: --show-all-vms Feature

## Test Environment Requirements

- Azure CLI authenticated
- At least one azlin-managed VM (has `managed-by=azlin` tag)
- At least one unmanaged VM (no `managed-by=azlin` tag)
- Access to resource group(s)

## Test Cases

### Test 1: Default Behavior (No Regression)
**Objective**: Verify existing behavior unchanged

```bash
cd /Users/ryan/src/azlin/worktrees/feat/issue-208-show-all-vms
export PYTHONPATH=src
python -m azlin.cli list
```

**Expected**:
- Shows ONLY azlin-managed VMs
- If unmanaged VMs exist, shows notification: `<n> additional vms not currently managed by azlin detected. Run with --show-all-vms to show them.`
- Table format unchanged
- Session names displayed correctly

**Status**: ⏳ Ready to test

---

### Test 2: Show All VMs Flag
**Objective**: Verify new flag shows all VMs

```bash
python -m azlin.cli list --show-all-vms
```

**Expected**:
- Shows ALL VMs (managed + unmanaged)
- Unmanaged VMs show "-" for session name
- No notification message (not needed when showing all)
- Table includes both types of VMs

**Status**: ⏳ Ready to test

---

### Test 3: Flag with --all (Include Stopped)
**Objective**: Verify flag works with --all

```bash
python -m azlin.cli list --show-all-vms --all
```

**Expected**:
- Shows ALL VMs including stopped/deallocated ones
- Works correctly with both managed and unmanaged VMs

**Status**: ⏳ Ready to test

---

### Test 4: Flag with --rg (Resource Group Filter)
**Objective**: Verify flag works with --rg

```bash
python -m azlin.cli list --show-all-vms --rg <resource-group-name>
```

**Expected**:
- Shows all VMs in specified resource group only
- Includes both managed and unmanaged VMs

**Status**: ⏳ Ready to test

---

### Test 5: Flag with --tag (Tag Filter)
**Objective**: Verify flag works with --tag

```bash
python -m azlin.cli list --show-all-vms --tag environment=dev
```

**Expected**:
- Shows all VMs with specified tag
- May exclude unmanaged VMs without the tag (expected behavior)

**Status**: ⏳ Ready to test

---

### Test 6: Notification Format (Singular)
**Objective**: Verify notification with 1 unmanaged VM

**Setup**: Ensure exactly 1 unmanaged VM exists

```bash
python -m azlin.cli list
```

**Expected**:
- Notification: `1 additional vm not currently managed by azlin detected. Run with --show-all-vms to show them.`
- Note: "vm" is singular, not "vms"

**Status**: ⏳ Ready to test

---

### Test 7: Notification Format (Plural)
**Objective**: Verify notification with multiple unmanaged VMs

**Setup**: Ensure 2+ unmanaged VMs exist

```bash
python -m azlin.cli list
```

**Expected**:
- Notification: `<n> additional vms not currently managed by azlin detected. Run with --show-all-vms to show them.`
- Note: "vms" is plural

**Status**: ⏳ Ready to test

---

### Test 8: No Notification When All Managed
**Objective**: Verify no notification when no unmanaged VMs exist

**Setup**: Ensure all VMs are azlin-managed

```bash
python -m azlin.cli list
```

**Expected**:
- Shows managed VMs normally
- NO notification message appears
- Normal output only

**Status**: ⏳ Ready to test

---

### Test 9: Help Text
**Objective**: Verify help text shows new flag

```bash
python -m azlin.cli list --help
```

**Expected**:
- `--show-all-vms` option listed
- Description: "Show all VMs (including unmanaged)"
- Examples section includes --show-all-vms usage

**Status**: ✅ **PASSED** - Verified in development

---

### Test 10: Edge Case - Empty Resource Group
**Objective**: Verify graceful handling of empty RG

```bash
python -m azlin.cli list --rg <empty-rg>
```

**Expected**:
- Shows "No VMs found" or similar message
- No crash or error
- Graceful degradation

**Status**: ⏳ Ready to test

---

## Test Results Summary

| Test | Status | Notes |
|------|--------|-------|
| Test 1: Default Behavior | ⏳ | Requires Azure VMs |
| Test 2: Show All VMs Flag | ⏳ | Requires Azure VMs |
| Test 3: With --all | ⏳ | Requires Azure VMs |
| Test 4: With --rg | ⏳ | Requires Azure VMs |
| Test 5: With --tag | ⏳ | Requires Azure VMs |
| Test 6: Notification (Singular) | ⏳ | Requires Azure VMs |
| Test 7: Notification (Plural) | ⏳ | Requires Azure VMs |
| Test 8: No Notification | ⏳ | Requires Azure VMs |
| Test 9: Help Text | ✅ | **PASSED** |
| Test 10: Empty RG | ⏳ | Requires Azure VMs |

---

## Notes

- All tests require working Azure CLI authentication
- Unit tests cover the logic (30 tests passing)
- Manual tests verify real Azure integration
- CI/CD will also validate these scenarios

---

## Quick Test Commands

```bash
# Navigate to worktree
cd /Users/ryan/src/azlin/worktrees/feat/issue-208-show-all-vms

# Set Python path
export PYTHONPATH=src

# Test default behavior
python -m azlin.cli list

# Test new flag
python -m azlin.cli list --show-all-vms

# Test with combinations
python -m azlin.cli list --show-all-vms --all
python -m azlin.cli list --show-all-vms --rg MY-RG

# Verify help
python -m azlin.cli list --help
```
