# Manual Testing Plan for Issue #455

## Overview
This document outlines the manual testing scenarios that should be performed to validate the fix for `azlin top` command with bastion and multiregion support.

## Automated Test Coverage
✅ 45 automated tests passing:
- Unit tests: SSH command building with ports, VMMetrics with region field, dashboard rendering
- Integration tests: SSHConnector integration, region metadata flow
- Security tests: Input validation, error sanitization

## Required Manual Testing Scenarios

### Test 1: Bastion Connection (Single VM)
**Setup:**
```bash
# Create VM with NO public IP (requires bastion)
azlin create test-bastion-vm --no-public-ip --size Standard_B2s --region eastus
```

**Test:**
```bash
azlin top
```

**Expected Results:**
- Dashboard shows "test-bastion-vm" with ONLINE status
- Metrics display: Load average, CPU%, Memory, Top process
- Region column shows "eastus"
- No SSH connection errors
- Dashboard updates every 10 seconds
- Ctrl+C exits cleanly

**Validation:**
- Check that SSH command includes `-p <port>` flag in logs/debug output
- Verify bastion tunnel is established (check Azure portal or logs)
- Confirm metrics are accurate compared to Azure portal metrics

### Test 2: Multi-Region VMs
**Setup:**
```bash
# Create VMs in different regions
azlin create vm-eastus --size Standard_B2s --region eastus
azlin create vm-westus2 --size Standard_B2s --region westus2
azlin create vm-centralus --size Standard_B2s --region centralus
```

**Test:**
```bash
azlin top
# Should show VMs from all regions
```

**Expected Results:**
- Dashboard shows ALL 3 VMs
- Region column displays correct regions: "eastus", "westus2", "centralus"
- Metrics collected from all VMs simultaneously
- Dashboard updates every 10 seconds
- All VMs show ONLINE status

**Validation:**
- Verify all VMs are discovered without explicit `--rg` flag
- Check that region information is accurate
- Confirm performance is acceptable with multiple regions

### Test 3: Mixed Bastion + Direct Connections
**Setup:**
```bash
# VM 1: eastus, with public IP (direct connection)
azlin create vm-public --size Standard_B2s --region eastus

# VM 2: westus2, no public IP (bastion required)
azlin create vm-bastion --no-public-ip --size Standard_B2s --region westus2
```

**Test:**
```bash
azlin top
```

**Expected Results:**
- Dashboard shows both VMs
- "vm-public" connects directly (< 100ms latency)
- "vm-bastion" connects via bastion (200-500ms latency)
- Both VMs show metrics
- Region column shows "eastus" and "westus2"
- Routing summary: "✓ 2 reachable (1 direct, 1 via bastion)"

**Validation:**
- Verify bastion is only used for VM without public IP
- Check connection methods in logs
- Confirm both connection types work simultaneously

### Test 4: Backwards Compatibility (Single RG with --rg flag)
**Setup:**
```bash
# Multiple VMs in one resource group
azlin create vm1 --rg my-test-rg --region eastus
azlin create vm2 --rg my-test-rg --region eastus
```

**Test:**
```bash
azlin top --rg my-test-rg
```

**Expected Results:**
- Dashboard shows only VMs from "my-test-rg"
- Command behavior identical to before fix
- Region column shows "eastus" for both
- No regression in functionality

**Validation:**
- Confirm `--rg` flag still works as expected
- Verify no breaking changes for existing users

### Test 5: Error Scenarios

**Test 5a: VM Not Responding**
```bash
# Stop a VM, then run azlin top
az vm stop --name test-vm --resource-group test-rg
azlin top
```

Expected: VM shows with error status, clear error message, other VMs still work

**Test 5b: Bastion Unavailable**
```bash
# Temporarily disable bastion, run azlin top
```

Expected: Clear error message about bastion unavailability, graceful degradation

**Test 5c: No VMs Found**
```bash
# Run in subscription with no azlin VMs
azlin top
```

Expected: Clear message "No VMs found" or similar, no errors

## UVX Testing (Branch Testing)
**Install from branch:**
```bash
uvx --from git+https://github.com/rysweet/azlin@fix/issue-455-top-bastion-multiregion azlin top
```

Run all above test scenarios using UVX installation to verify the fix works in real deployment.

## Performance Benchmarks
- **Direct connection latency:** < 100ms (baseline)
- **Bastion connection latency:** 200-500ms (expected overhead)
- **Multi-region discovery startup:** +1-2 seconds (query all RGs)
- **Dashboard refresh rate:** 10 seconds (configurable with `--interval`)
- **Max concurrent VMs:** 10 (default `max_workers`, configurable)

## Success Criteria
All manual tests must pass before merging:
- ✅ Bastion connections work (Test 1)
- ✅ Multi-region VMs displayed (Test 2)
- ✅ Mixed connection types work (Test 3)
- ✅ Backwards compatibility maintained (Test 4)
- ✅ Error scenarios handled gracefully (Test 5)
- ✅ UVX installation works (Branch testing)

## Notes for Reviewers
- Manual testing requires active Azure subscription with appropriate permissions
- Tests should be performed in a dev/test subscription, not production
- All test VMs should be cleaned up after testing
- Performance may vary based on network conditions and Azure region load
