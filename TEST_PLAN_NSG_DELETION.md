# Test Plan: NSG Deletion in azlin destroy

## Issue #516 - Destroy does not delete Network Security Groups

### Test Objective
Verify that `azlin destroy` now correctly deletes all resources including NSGs.

### Pre-Test Setup
1. Create a test VM with azlin:
   ```bash
   azlin new --name test-nsg-vm --size s
   ```

2. Verify NSG was created:
   ```bash
   az network nsg list --resource-group rysweet-linux-vm-pool --query "[?contains(name, 'test-nsg-vm')].name" -o tsv
   ```
   Expected: Should show NSG named like `test-nsg-vmNSG`

### Test Case 1: Single VM Destroy with NSG
**Scenario**: Destroy a VM and verify NSG is deleted

1. Run destroy command:
   ```bash
   azlin destroy --force test-nsg-vm
   ```

2. Verify output includes NSG deletion:
   ```
   Expected output should mention:
   - VM: test-nsg-vm
   - NIC: test-nsg-vmVMNic
   - NSG: test-nsg-vmNSG
   - Disk: test-nsg-vm_OsDisk_...
   ```

3. Verify NSG was actually deleted:
   ```bash
   az network nsg show --name test-nsg-vmNSG --resource-group rysweet-linux-vm-pool
   ```
   Expected: Should fail with "ResourceNotFound"

4. Verify can create new VM with same name:
   ```bash
   azlin new --name test-nsg-vm --size s
   ```
   Expected: Should succeed without "Resource already exists" error

### Test Case 2: Dry-Run Shows NSG
**Scenario**: Verify dry-run lists NSG that would be deleted

1. Create test VM:
   ```bash
   azlin new --name test-dry-run --size s
   ```

2. Run dry-run:
   ```bash
   azlin destroy --dry-run test-dry-run
   ```

3. Verify output mentions NSG:
   ```
   Expected output should list:
   - Associated NSGs
   ```

### Test Case 3: Cleanup Orphaned NSGs
**Scenario**: Clean up existing orphaned NSGs from before this fix

1. List all NSGs in resource group:
   ```bash
   az network nsg list --resource-group rysweet-linux-vm-pool --query "[].{Name:name, Tags:tags}" -o table
   ```

2. Identify orphaned NSGs (NSGs with azlin tags but no corresponding VM):
   ```bash
   # For each NSG, check if corresponding VM exists
   # If VM doesn't exist, NSG is orphaned
   ```

3. Delete orphaned NSGs:
   ```bash
   az network nsg delete --name <orphaned-nsg-name> --resource-group rysweet-linux-vm-pool
   ```

### Test Case 4: VM with No NSG (Edge Case)
**Scenario**: Verify destroy works when NIC has no NSG attached

1. This would require creating a VM with a custom network configuration
2. Expected: Destroy should succeed gracefully, logging debug message about no NSG

### Test Results Template
```markdown
## Test Execution Results

**Date**: [Date]
**Tester**: [Name]
**Branch**: feat/issue-516-destroy-nsg-deletion

### Test Case 1: Single VM Destroy with NSG
- [ ] VM created successfully
- [ ] NSG verified to exist
- [ ] Destroy command executed
- [ ] Output shows NSG deletion
- [ ] NSG verified deleted
- [ ] Can create new VM with same name
- **Result**: PASS / FAIL
- **Notes**:

### Test Case 2: Dry-Run Shows NSG
- [ ] VM created
- [ ] Dry-run executed
- [ ] Output mentions NSGs
- **Result**: PASS / FAIL
- **Notes**:

### Test Case 3: Cleanup Orphaned NSGs
- [ ] Orphaned NSGs identified
- [ ] Orphaned NSGs deleted
- [ ] Resource group clean
- **Result**: PASS / FAIL
- **Notes**:

### Test Case 4: VM with No NSG
- [ ] Test skipped (requires custom setup)
- **Result**: SKIPPED / PASS / FAIL
- **Notes**:

## Overall Assessment
- All critical tests passed: YES / NO
- Ready for merge: YES / NO
- Issues found:
```

### Success Criteria
- ✅ Destroy command deletes NSGs
- ✅ Dry-run shows NSGs in deletion list
- ✅ Can reuse VM names after destroy
- ✅ No orphaned NSGs remain
- ✅ Error handling graceful (no crashes)

### Notes
- This fix resolves issue #516
- NSG deletion is best-effort (if NSG doesn't exist, destroy continues)
- NSGs discovered by querying each NIC for its associated NSG
