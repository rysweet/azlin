# Backup and Disaster Recovery

Automated backup scheduling, cross-region replication, backup verification, and disaster recovery testing for azlin-managed Azure VMs.

## Quick Start

```bash
# Configure automated backups with 7-day daily retention
azlin backup configure my-vm --daily-retention 7

# Trigger a backup immediately
azlin backup trigger my-vm

# List all backups
azlin backup list my-vm

# Restore from a backup
azlin backup restore my-vm --backup my-vm-backup-daily-20251201
```

## Contents

- [Backup Configuration](#backup-configuration)
- [Backup Operations](#backup-operations)
- [Cross-Region Replication](#cross-region-replication)
- [Backup Verification](#backup-verification)
- [Disaster Recovery Testing](#disaster-recovery-testing)
- [DR Runbooks](#dr-runbooks)
- [Monitoring and Alerts](#monitoring-and-alerts)
- [Troubleshooting](#troubleshooting)

## Backup Configuration

### Configure Backup Schedule

Set up automated backup policies with tiered retention:

```bash
# Basic daily backups (7 days retention)
azlin backup configure prod-db-vm \
  --daily-retention 7

# Full retention policy: daily + weekly + monthly
azlin backup configure prod-app-vm \
  --daily-retention 7 \
  --weekly-retention 4 \
  --monthly-retention 12

# With cross-region replication for geo-redundancy
azlin backup configure critical-vm \
  --daily-retention 7 \
  --weekly-retention 4 \
  --monthly-retention 12 \
  --cross-region \
  --target-region westus2
```

**Output:**
```
✓ Backup schedule configured for prod-db-vm
  Daily retention: 7 days
  Weekly retention: 4 weeks
  Monthly retention: 12 months
  Cross-region replication: enabled → westus2

Configuration saved to VM tags (azlin:backup-schedule)
```

### View Current Configuration

```bash
# Show backup configuration for a VM
azlin backup config-show prod-db-vm
```

**Output:**
```
Backup Configuration for prod-db-vm:
  Status: Enabled
  Daily retention: 7 days (last: 2025-12-01 08:00)
  Weekly retention: 4 weeks (last: 2025-11-24 08:00)
  Monthly retention: 12 months (last: 2025-12-01 08:00)
  Cross-region: enabled → westus2
  Total backups: 23 (daily: 7, weekly: 4, monthly: 12)
```

### Disable Backups

```bash
# Disable automated backups (preserves existing backups)
azlin backup disable prod-db-vm
```

## Backup Operations

### Trigger Backup Manually

Backups are automatically assigned retention tiers based on schedule:

- **Daily**: Every day
- **Weekly**: First backup of each week (Sunday)
- **Monthly**: First backup of each month (1st day)

```bash
# Automatic tier selection (daily/weekly/monthly determined by date)
azlin backup trigger prod-db-vm

# Force specific tier (override automatic selection)
azlin backup trigger prod-db-vm --tier weekly
```

**Output:**
```
Creating backup for prod-db-vm...
  Retention tier: daily (7 days)
  Snapshot: prod-db-vm-backup-daily-20251201-0800

✓ Backup created successfully
  Size: 128 GB
  Time: 3m 42s
  Cross-region replication: queued → westus2
```

### List Backups

```bash
# List all backups for a VM
azlin backup list prod-db-vm

# Filter by retention tier
azlin backup list prod-db-vm --tier weekly

# Filter by time range
azlin backup list prod-db-vm --since 7d
```

**Output:**
```
Backups for prod-db-vm (23 total):

Daily (7):
  prod-db-vm-backup-daily-20251201-0800  128 GB  verified ✓  replicated ✓
  prod-db-vm-backup-daily-20251130-0800  128 GB  verified ✓  replicated ✓
  prod-db-vm-backup-daily-20251129-0800  128 GB  verified ✓  replicated ✓
  ...

Weekly (4):
  prod-db-vm-backup-weekly-20251124-0800  128 GB  verified ✓  replicated ✓
  prod-db-vm-backup-weekly-20251117-0800  128 GB  verified ✓  replicated ✓
  ...

Monthly (12):
  prod-db-vm-backup-monthly-20251201-0800  128 GB  verified ✓  replicated ✓
  prod-db-vm-backup-monthly-20251101-0800  128 GB  verified ✓  replicated ✓
  ...
```

### Restore from Backup

Point-in-time recovery to any backup:

```bash
# Restore specific backup (replaces VM disk)
azlin backup restore prod-db-vm \
  --backup prod-db-vm-backup-daily-20251201-0800

# Interactive selection from available backups
azlin backup restore prod-db-vm --interactive

# Restore to new VM (preserves original)
azlin backup restore prod-db-vm \
  --backup prod-db-vm-backup-daily-20251201-0800 \
  --new-vm prod-db-vm-restored
```

**Output:**
```
Restoring prod-db-vm from backup...
  Backup: prod-db-vm-backup-daily-20251201-0800
  Size: 128 GB
  Created: 2025-12-01 08:00:00 UTC

⚠ WARNING: This will replace the VM's OS disk
  Current VM will be stopped during restore
  Estimated downtime: 10-15 minutes

Proceed? (yes/no): yes

Stopping VM...
Swapping OS disk...
Starting VM...

✓ Restore complete
  RTO (Recovery Time): 12m 34s
  VM status: Running
  SSH connectivity: verified
```

## Cross-Region Replication

Replicate backups to secondary region for geo-redundancy and disaster recovery.

### Replicate Specific Backup

```bash
# Replicate single backup to target region
azlin backup replicate prod-db-vm-backup-daily-20251201-0800 \
  --target-region westus2
```

**Output:**
```
Replicating backup to westus2...
  Source: prod-db-vm-backup-daily-20251201-0800 (eastus)
  Target: prod-db-vm-backup-daily-20251201-0800 (westus2)
  Size: 128 GB

Replication started (job ID: 1234)
Estimated time: 10-15 minutes

Track progress: azlin backup replication-status prod-db-vm
```

### Replicate All Unreplicated Backups

```bash
# Replicate all backups missing in target region
azlin backup replicate-all prod-db-vm --target-region westus2

# With parallel replication (max 3 concurrent)
azlin backup replicate-all prod-db-vm \
  --target-region westus2 \
  --max-parallel 3
```

**Output:**
```
Found 5 unreplicated backups for prod-db-vm

Replicating in parallel (max 3):
  [1/5] prod-db-vm-backup-daily-20251201-0800  ⟳ in progress
  [2/5] prod-db-vm-backup-daily-20251130-0800  ⟳ in progress
  [3/5] prod-db-vm-backup-daily-20251129-0800  ⟳ in progress
  [4/5] prod-db-vm-backup-daily-20251128-0800  ⏸ queued
  [5/5] prod-db-vm-backup-daily-20251127-0800  ⏸ queued

✓ All replications complete (5/5 succeeded)
  Total time: 18m 42s
```

### Check Replication Status

```bash
# Show replication status for VM
azlin backup replication-status prod-db-vm

# List all replication jobs
azlin backup replication-jobs

# Filter by status
azlin backup replication-jobs --status pending
azlin backup replication-jobs --status failed
```

**Output:**
```
Replication Status for prod-db-vm:

In Progress (2):
  Job 1234: daily-20251201-0800 → westus2  [███████░░░] 70%  ETA: 3m
  Job 1235: daily-20251130-0800 → westus2  [████░░░░░░] 45%  ETA: 7m

Completed (18):
  Job 1230: daily-20251129-0800 → westus2  ✓  12m 34s
  Job 1229: weekly-20251124-0800 → westus2  ✓  14m 12s
  ...

Failed (0):
  (no failed replications)
```

## Backup Verification

Verify backup integrity by creating temporary test disks without disrupting production VMs.

### Verify Single Backup

```bash
# Verify backup can be restored
azlin backup verify prod-db-vm-backup-daily-20251201-0800
```

**Output:**
```
Verifying backup prod-db-vm-backup-daily-20251201-0800...

Creating test disk from snapshot...  ✓
Verifying disk properties...          ✓
  - Size matches: 128 GB
  - Status: Ready
  - Readable: Yes
Deleting test disk...                 ✓

✓ Backup verified successfully
  Verification time: 1m 48s
  Result: PASS - backup is restorable
```

### Verify All Backups

```bash
# Verify all unverified backups for VM
azlin backup verify-all prod-db-vm

# With parallel verification
azlin backup verify-all prod-db-vm --max-parallel 2
```

**Output:**
```
Found 7 unverified backups for prod-db-vm

Verifying in parallel (max 2):
  [1/7] daily-20251201-0800  ✓  1m 42s
  [2/7] daily-20251130-0800  ✓  1m 55s
  [3/7] daily-20251129-0800  ✓  1m 38s
  [4/7] daily-20251128-0800  ✓  1m 51s
  [5/7] daily-20251127-0800  ✓  1m 44s
  [6/7] daily-20251126-0800  ✓  1m 49s
  [7/7] daily-20251125-0800  ✓  1m 46s

✓ All verifications complete (7/7 passed)
  Total time: 6m 25s
  Success rate: 100%
```

### Verification Report

```bash
# Show verification report for last 7 days
azlin backup verification-report --vm prod-db-vm --days 7

# All VMs in resource group
azlin backup verification-report --days 30
```

**Output:**
```
Backup Verification Report (Last 7 Days)

VM: prod-db-vm
  Total backups: 23
  Verified: 23 (100%)
  Success rate: 100% (23/23 passed)
  Last verified: 2025-12-01 10:30:00 UTC

  Failed verifications: 0
  Unverified backups: 0

Overall Statistics:
  Total backups across all VMs: 145
  Verified: 145 (100%)
  Success rate: 99.3% (144/145 passed)

Failed Verifications:
  staging-vm-backup-daily-20251125-0800
    Error: Disk size mismatch (expected 64GB, got 0GB)
    Action required: Recreate backup
```

## Disaster Recovery Testing

Automated DR testing validates complete restore workflows including VM boot and connectivity.

### Run DR Test

Full disaster recovery test in secondary region:

```bash
# Basic DR test (latest backup to secondary region)
azlin dr test prod-db-vm \
  --test-region westus2

# Test specific backup
azlin dr test prod-db-vm \
  --backup prod-db-vm-backup-weekly-20251124-0800 \
  --test-region westus2

# With custom resource group
azlin dr test prod-db-vm \
  --backup prod-db-vm-backup-daily-20251201-0800 \
  --test-region westus2 \
  --test-resource-group DR-Testing
```

**Output:**
```
Starting DR test for prod-db-vm...
  Backup: prod-db-vm-backup-daily-20251201-0800
  Test region: westus2
  Test VM: prod-db-vm-dr-test-20251201

Phase 1: Restore backup to test VM...     ✓  8m 32s
Phase 2: Verify VM boots successfully...  ✓  2m 15s
Phase 3: Verify SSH connectivity...       ✓  0m 08s
Phase 4: Cleanup test resources...        ✓  1m 45s

✓ DR test PASSED
  RTO (Recovery Time Objective): 10m 47s
  Target: <15 minutes ✓

  Test results:
    - Restore: SUCCESS
    - Boot: SUCCESS
    - Connectivity: SUCCESS
    - Cleanup: SUCCESS
```

### Run All Scheduled DR Tests

```bash
# Run weekly DR tests for all VMs with DR enabled
azlin dr test-all

# With specific resource group
azlin dr test-all --resource-group Production-VMs
```

**Output:**
```
Running scheduled DR tests...

[1/3] prod-db-vm      ✓  11m 23s  RTO: 11m 23s
[2/3] prod-app-vm     ✓  9m 47s   RTO: 9m 47s
[3/3] critical-vm     ✓  12m 15s  RTO: 12m 15s

✓ All DR tests passed (3/3)
  Average RTO: 11m 08s
  Target: <15 minutes ✓
  Success rate: 100%
```

### DR Test History

```bash
# Show DR test history for VM (last 30 days)
azlin dr test-history prod-db-vm --days 30

# All VMs
azlin dr test-history --days 90
```

**Output:**
```
DR Test History for prod-db-vm (Last 30 Days)

Recent Tests (4):
  2025-12-01 10:00  ✓ PASS  RTO: 10m 47s  westus2
  2025-11-24 10:00  ✓ PASS  RTO: 11m 23s  westus2
  2025-11-17 10:00  ✓ PASS  RTO: 9m 58s   westus2
  2025-11-10 10:00  ✓ PASS  RTO: 12m 04s  westus2

Statistics:
  Total tests: 4
  Passed: 4 (100%)
  Failed: 0 (0%)
  Average RTO: 11m 03s
  Max RTO: 12m 04s (within 15m target ✓)
```

### DR Success Rate

```bash
# Show success rate for VM
azlin dr success-rate --vm prod-db-vm --days 90

# All VMs
azlin dr success-rate --days 90
```

**Output:**
```
DR Success Rate (Last 90 Days)

VM: prod-db-vm
  Total tests: 12
  Passed: 12 (100%)
  Failed: 0 (0%)
  Success rate: 100% ✓
  Target: 99.9%

Overall (All VMs):
  Total tests: 36
  Passed: 36 (100%)
  Failed: 0 (0%)
  Success rate: 100% ✓
  Target: 99.9% ✓

Compliance: PASSING
```

## DR Runbooks

Disaster recovery procedures for common scenarios.

### Scenario 1: VM Corruption - Point-in-Time Restore

**When**: VM disk corrupted, need restore to last known good state
**RTO Target**: <15 minutes

```bash
# Step 1: List available backups
azlin backup list prod-db-vm

# Step 2: Select and restore latest working backup
azlin backup restore prod-db-vm \
  --backup prod-db-vm-backup-daily-20251201-0800

# Step 3: Verify VM after restore
azlin ssh prod-db-vm "systemctl status"
```

**Expected Result**: VM restored and operational in <15 minutes

### Scenario 2: Region Outage - Cross-Region Failover

**When**: Primary region unavailable, fail over to secondary region
**RTO Target**: <15 minutes (restore) + DNS propagation

```bash
# Step 1: Verify recent backup replicated to secondary region
azlin backup replication-status prod-db-vm

# Step 2: Restore in secondary region
azlin dr test prod-db-vm \
  --backup prod-db-vm-backup-daily-20251201-0800 \
  --test-region westus2

# Step 3: Update DNS/load balancer to point to new VM
# (manual step - update your DNS configuration)

# Step 4: Verify connectivity
ssh user@prod-db-vm.westus2.cloudapp.azure.com
```

**Expected Result**: Service restored in secondary region, accessible after DNS propagation

### Scenario 3: Data Loss - Restore to Specific Point in Time

**When**: Accidental data deletion, need restore to before deletion
**RTO Target**: <15 minutes

```bash
# Step 1: Find backup before deletion (2025-12-01 07:00)
azlin backup list prod-db-vm --since 7d

# Step 2: Verify backup integrity
azlin backup verify prod-db-vm-backup-daily-20251201-0700

# Step 3: Restore selected backup
azlin backup restore prod-db-vm \
  --backup prod-db-vm-backup-daily-20251201-0700

# Step 4: Verify data restored
azlin ssh prod-db-vm "ls -la /data/critical-files"
```

**Expected Result**: Data restored to state before deletion

### Scenario 4: Compliance Testing - Quarterly DR Drill

**When**: Scheduled compliance requirement for DR testing
**Target**: 99.9% success rate

```bash
# Step 1: Run DR tests for all VMs
azlin dr test-all

# Step 2: Verify success rate meets target
azlin dr success-rate --days 90

# Step 3: Verify all backups tested
azlin backup verification-report --days 90

# Step 4: Generate compliance report
azlin dr test-history --days 90 > quarterly-dr-report.txt
```

**Expected Result**: All DR tests pass, 99.9%+ success rate, compliance report generated

## Monitoring and Alerts

Backup and DR operations integrate with azlin monitoring system for alerting.

### Alert Configuration

Configure alerts in `~/.azlin/alerts.yaml`:

```yaml
# Backup failure alerts
backup_failure:
  enabled: true
  severity: high
  channels: [slack, email]

# DR test failure alerts
dr_test_failure:
  enabled: true
  severity: critical
  channels: [slack, email, webhook]

# RTO threshold exceeded
rto_exceeded:
  enabled: true
  severity: high
  threshold_minutes: 15
  channels: [slack]

# Verification failure alerts
verification_failure:
  enabled: true
  severity: high
  channels: [slack, email]

# Unverified backups (backups not verified for >7 days)
verification_overdue:
  enabled: true
  severity: medium
  threshold_days: 7
  channels: [slack]
```

### Alert Types

**Backup Alerts**:
- Backup creation failed
- Retention policy violation (cleanup failed)
- Replication to secondary region failed

**DR Alerts**:
- DR test failed (restore/boot/connectivity)
- RTO threshold exceeded (>15 minutes)
- Success rate below target (<99.9%)

**Verification Alerts**:
- Backup verification failed (not restorable)
- Backups unverified for >7 days

## Troubleshooting

### Backup Creation Fails

**Symptoms**: `azlin backup trigger` fails with snapshot creation error

**Causes**:
- Insufficient permissions (need `Contributor` or `Disk Backup Reader` role)
- VM not found or deleted
- Resource group locked
- Azure quota exceeded

**Solution**:
```bash
# Check VM exists and status
az vm show --name prod-db-vm --resource-group Production

# Verify permissions
az role assignment list --assignee $(az account show --query user.name -o tsv)

# Check Azure quota
az vm list-usage --location eastus -o table
```

### Replication Stuck "In Progress"

**Symptoms**: Cross-region replication job stuck for >30 minutes

**Causes**:
- Network connectivity issues between regions
- Target region quota exceeded
- Source snapshot deleted during replication

**Solution**:
```bash
# Check replication status
azlin backup replication-jobs --status in_progress

# Cancel stuck job (will retry automatically)
az snapshot show --name target-snapshot-name --resource-group Production

# Retry replication manually
azlin backup replicate source-snapshot-name --target-region westus2
```

### Verification Fails - Disk Size Mismatch

**Symptoms**: Backup verification reports size mismatch

**Causes**:
- Snapshot corrupted during creation
- Storage account issues
- Azure platform issue

**Solution**:
```bash
# Check snapshot details
az snapshot show --name backup-name --resource-group Production

# Recreate backup (will create new snapshot)
azlin backup trigger prod-db-vm --tier daily

# Verify new backup
azlin backup verify prod-db-vm-backup-daily-20251201-0900
```

### DR Test Fails - VM Won't Boot

**Symptoms**: DR test fails at boot verification phase

**Causes**:
- Backup from VM in crashed state
- Network security group blocks connectivity
- Azure region capacity issues

**Solution**:
```bash
# Check backup creation time (was VM healthy?)
azlin backup list prod-db-vm

# Try earlier backup from known-good state
azlin dr test prod-db-vm \
  --backup prod-db-vm-backup-weekly-20251124-0800 \
  --test-region westus2

# Check test VM status in Azure portal
az vm show --name prod-db-vm-dr-test-20251201 --resource-group DR-Testing
```

### High Storage Costs

**Symptoms**: Backup storage costs higher than expected

**Causes**:
- Too many retention tiers enabled
- Cross-region replication doubling costs
- Large VM disks

**Solution**:
```bash
# Review current retention policy
azlin backup config-show prod-db-vm

# Reduce retention (fewer backups kept)
azlin backup configure prod-db-vm \
  --daily-retention 3 \
  --weekly-retention 2 \
  --monthly-retention 6

# Disable cross-region for non-critical VMs
azlin backup configure staging-vm \
  --daily-retention 3 \
  --no-cross-region
```

**Cost Optimization Tips**:
- Use daily-only retention for dev/staging VMs (3-7 days)
- Enable cross-region replication only for critical production VMs
- Reduce monthly retention to 6 months for non-compliance workloads
- Schedule cleanup to run after each backup

---

## Related Documentation

- [Snapshot Management](./snapshots.md) - Manual snapshot operations (foundation for backups)
- [Monitoring and Alerting](./monitoring.md) - Configure alerts for backup/DR failures
- [Azure Regions](./azure-regions.md) - Supported regions for cross-region replication
- [Cost Management](./cost-management.md) - Optimize backup storage costs

## Cost Estimates

**Per VM Monthly Costs** (based on 128GB disk):

| Configuration | Storage Cost | Compute Cost | Total |
|---------------|--------------|--------------|-------|
| Daily only (7 days) | ~$45 | ~$2 | ~$47 |
| Daily + Weekly + Monthly | ~$148 | ~$2 | ~$150 |
| With cross-region replication | ~$296 | ~$12 | ~$308 |

**Cost Breakdown**:
- Daily backups (7 × 128GB): $45/month
- Weekly backups (4 × 128GB): $26/month
- Monthly backups (12 × 128GB): $77/month
- Cross-region replication: 2× storage costs
- DR test VMs (4 hours/month): $10/month
- Verification test disks: $2/month

See [Azure Snapshot Pricing](https://azure.microsoft.com/en-us/pricing/details/managed-disks/) for current rates.

---

**Last Updated**: 2025-12-01
**Applies To**: azlin v0.8.0+
**Feature Status**: [PLANNED - Implementation Pending]
