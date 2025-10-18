# Manual Testing Plan - Azure Files NFS Feature

**Feature**: Azure Files NFS integration for shared home directories  
**Issue**: #66  
**Date**: October 18, 2025  
**Status**: Step 8 - Manual Testing Plan (Awaiting Execution)

---

## Prerequisites

Before running manual tests, ensure:
- [ ] Azure CLI installed and configured (`az login`)
- [ ] Valid Azure subscription with permissions
- [ ] SSH keys generated (`~/.azlin/ssh/azlin_key`)
- [ ] azlin CLI installed and working
- [ ] Sufficient Azure quota (3 VMs, 1 storage account)

---

## Test Scenario 1: Create Storage Account

**Objective**: Verify storage account creation with NFS enabled

### Steps:
1. Create storage account:
   ```bash
   azlin storage create test-shared-dev --tier Premium --size 100GB
   ```

### Expected Results:
- [ ] Storage account created in Azure
- [ ] NFS v4.1 enabled
- [ ] VNet-only access configured
- [ ] File share "home" created with 100GB quota
- [ ] Tagged with `managed-by=azlin`
- [ ] Command outputs storage details

### Verification:
```bash
az storage account show --name testshareddev --resource-group <rg> --query '{name:name,nfs:enableNfsV3,sku:sku.name}'
```

---

## Test Scenario 2: List Storage Accounts

**Objective**: Verify listing shows only azlin-managed storage

### Steps:
1. List storage accounts:
   ```bash
   azlin storage list
   ```

### Expected Results:
- [ ] Shows test-shared-dev
- [ ] Displays tier, size, region
- [ ] Filters to only azlin-managed accounts

---

## Test Scenario 3: Provision VM with Shared Home

**Objective**: Create VM with NFS-mounted home directory

### Steps:
1. Provision first VM:
   ```bash
   azlin new --shared-home test-shared-dev --name worker-1
   ```

2. SSH into VM:
   ```bash
   azlin ssh worker-1
   ```

3. Verify mount:
   ```bash
   mount | grep /home/azureuser
   df -h /home/azureuser
   cat /etc/fstab | grep nfs
   ```

### Expected Results:
- [ ] VM provisioned successfully
- [ ] Home directory is NFS-mounted
- [ ] Mount persists in /etc/fstab
- [ ] Ownership is azureuser:azureuser
- [ ] Can read and write files

---

## Test Scenario 4: Multi-VM File Sharing

**Objective**: Verify multiple VMs share same home directory

### Steps:
1. Provision second VM:
   ```bash
   azlin new --shared-home test-shared-dev --name worker-2
   ```

2. On worker-1, create test file:
   ```bash
   azlin ssh worker-1
   echo "Hello from worker-1" > ~/shared-test.txt
   date > ~/timestamp.txt
   exit
   ```

3. On worker-2, verify file exists:
   ```bash
   azlin ssh worker-2
   cat ~/shared-test.txt
   cat ~/timestamp.txt
   exit
   ```

4. On worker-2, append to file:
   ```bash
   azlin ssh worker-2
   echo "Hello from worker-2" >> ~/shared-test.txt
   exit
   ```

5. On worker-1, verify append:
   ```bash
   azlin ssh worker-1
   cat ~/shared-test.txt
   exit
   ```

### Expected Results:
- [ ] File created on worker-1 visible on worker-2
- [ ] File modified on worker-2 reflects on worker-1
- [ ] No data loss or corruption
- [ ] Timestamps update correctly

---

## Test Scenario 5: Attach Existing VM

**Objective**: Attach pre-existing VM to shared storage

### Steps:
1. Create VM without shared storage:
   ```bash
   azlin new --name worker-3
   ```

2. Create files in local home:
   ```bash
   azlin ssh worker-3
   echo "Local file" > ~/local-file.txt
   mkdir ~/local-dir
   echo "data" > ~/local-dir/data.txt
   exit
   ```

3. Attach to shared storage:
   ```bash
   azlin storage attach test-shared-dev --vm worker-3
   ```

4. Verify files:
   ```bash
   azlin ssh worker-3
   ls -la ~/
   cat ~/local-file.txt
   cat ~/shared-test.txt  # From previous test
   exit
   ```

### Expected Results:
- [ ] Local files backed up before mount
- [ ] Local files copied to shared storage
- [ ] Shared files from other VMs visible
- [ ] No data loss
- [ ] Backup created at `/home/azureuser.backup`

---

## Test Scenario 6: Storage Status

**Objective**: Verify storage status reporting

### Steps:
1. Check storage status:
   ```bash
   azlin storage status test-shared-dev
   ```

### Expected Results:
- [ ] Shows tier (Premium)
- [ ] Shows size (100GB)
- [ ] Shows utilization (used GB and percentage)
- [ ] Lists connected VMs (worker-1, worker-2, worker-3)
- [ ] Shows cost per month ($15.36)
- [ ] Shows NFS endpoint

---

## Test Scenario 7: Detach VM

**Objective**: Detach VM from shared storage

### Steps:
1. Detach worker-3:
   ```bash
   azlin storage detach --vm worker-3
   ```

2. Verify detachment:
   ```bash
   azlin ssh worker-3
   mount | grep /home/azureuser
   ls -la ~/
   cat ~/local-file.txt
   cat ~/shared-test.txt  # Should still exist (copied local)
   exit
   ```

### Expected Results:
- [ ] NFS unmounted
- [ ] Files copied to local disk
- [ ] Files still accessible
- [ ] fstab entry removed
- [ ] Can still read/write files

---

## Test Scenario 8: VM Reboot Persistence

**Objective**: Verify NFS mount persists after reboot

### Steps:
1. Reboot worker-1:
   ```bash
   azlin ssh worker-1 -- sudo reboot
   ```

2. Wait 60 seconds, then reconnect:
   ```bash
   sleep 60
   azlin ssh worker-1
   mount | grep /home/azureuser
   cat ~/shared-test.txt
   exit
   ```

### Expected Results:
- [ ] NFS automatically remounted on boot
- [ ] Files still accessible
- [ ] No data loss

---

## Test Scenario 9: Concurrent File Access

**Objective**: Test concurrent writes from multiple VMs

### Steps:
1. On worker-1 (background):
   ```bash
   azlin ssh worker-1 -- 'for i in {1..100}; do echo "worker-1-$i" >> ~/concurrent.txt; sleep 0.1; done' &
   ```

2. On worker-2 (background):
   ```bash
   azlin ssh worker-2 -- 'for i in {1..100}; do echo "worker-2-$i" >> ~/concurrent.txt; sleep 0.1; done' &
   ```

3. Wait for completion, then verify:
   ```bash
   wait
   azlin ssh worker-1 -- 'wc -l ~/concurrent.txt'
   azlin ssh worker-1 -- 'grep -c worker-1 ~/concurrent.txt'
   azlin ssh worker-1 -- 'grep -c worker-2 ~/concurrent.txt'
   ```

### Expected Results:
- [ ] 200 total lines written
- [ ] 100 lines from worker-1
- [ ] 100 lines from worker-2
- [ ] No corrupted lines
- [ ] NFS file locking works correctly

---

## Test Scenario 10: Delete Storage (Safety)

**Objective**: Verify deletion safety checks

### Steps:
1. Try to delete with connected VMs:
   ```bash
   azlin storage delete test-shared-dev
   ```

### Expected Results:
- [ ] Error: "VMs still connected"
- [ ] Lists worker-1, worker-2
- [ ] Suggests detaching first or using --force
- [ ] Storage NOT deleted

---

## Test Scenario 11: Cleanup

**Objective**: Clean up all test resources

### Steps:
1. Detach all VMs:
   ```bash
   azlin storage detach --vm worker-1
   azlin storage detach --vm worker-2
   ```

2. Delete VMs:
   ```bash
   azlin delete worker-1 worker-2 worker-3 --yes
   ```

3. Delete storage:
   ```bash
   azlin storage delete test-shared-dev --force
   ```

4. Verify cleanup:
   ```bash
   azlin list
   azlin storage list
   ```

### Expected Results:
- [ ] All VMs deleted
- [ ] Storage account deleted
- [ ] No orphaned resources
- [ ] Clean state

---

## Performance Tests

### Test P1: Large File Transfer
```bash
# On worker-1
dd if=/dev/zero of=~/large-file.bin bs=1M count=1024  # 1GB file
time rsync -avh ~/large-file.bin worker-2:~/

# Expected: < 2 minutes for 1GB
```

### Test P2: Many Small Files
```bash
# On worker-1
mkdir ~/small-files
for i in {1..1000}; do echo "file $i" > ~/small-files/file-$i.txt; done
time ls -la ~/small-files/ | wc -l

# Expected: < 10 seconds for 1000 files
```

---

## Error Handling Tests

### Test E1: Network Interruption
1. Mount NFS storage
2. Disconnect network temporarily
3. Try to access files
4. Reconnect network
5. Verify auto-recovery

### Test E2: Storage Full
1. Fill storage to 100%
2. Try to write new file
3. Verify error message
4. Clean up space
5. Verify recovery

### Test E3: Invalid Storage Name
```bash
azlin storage create "invalid name!" --tier Premium
# Expected: ValidationError with clear message
```

---

## Documentation Checklist

After manual testing:
- [ ] Document actual performance metrics
- [ ] Note any issues or bugs found
- [ ] Update requirements with real-world findings
- [ ] Add troubleshooting guide
- [ ] Update README with usage examples

---

## Success Criteria

To pass manual testing, all of the following must be true:

- [ ] All 11 test scenarios pass
- [ ] Performance tests meet targets (<2min for 1GB, <10sec for 1000 files)
- [ ] Error handling graceful and clear
- [ ] No data loss in any scenario
- [ ] NFS mounts persist across reboots
- [ ] Concurrent access works correctly
- [ ] Safety checks prevent accidental deletion
- [ ] Cleanup leaves no orphaned resources

---

## Known Limitations

Document any limitations discovered:
- NFS performance vs local disk: ____%
- Max concurrent VMs tested: ____
- Max file size tested: ____
- Network latency impact: ____

---

## Next Steps After Manual Testing

1. Document results in TEST_RESULTS.md
2. Fix any bugs found
3. Update documentation
4. Proceed to Step 9 (Open Pull Request)

---

*Manual testing plan created on October 18, 2025*  
*To be executed before production deployment*
