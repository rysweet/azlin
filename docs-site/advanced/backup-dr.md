# Backup & Disaster Recovery

Automated backup management, disaster recovery testing, and business continuity for Azure VM infrastructure.

## Overview

azlin v0.4.0 provides enterprise-grade backup and disaster recovery capabilities to protect your VM data and ensure business continuity.

**Key Features:**

- **Automated Backups**: Schedule and manage VM snapshots automatically
- **Backup Verification**: Test backup integrity regularly
- **DR Testing**: Simulate disasters without affecting production
- **Point-in-Time Recovery**: Restore VMs to specific timestamps
- **Cross-Region Backup**: Replicate backups across regions
- **Compliance Reporting**: Generate backup compliance reports

## Quick Start

### Enable Automated Backups

```bash
# Enable daily backups
azlin backup enable myvm --schedule daily --retention 30d

# Enable with custom schedule
azlin backup enable myvm \
  --schedule "0 2 * * *" \
  --retention 90d \
  --compress \
  --verify

# Output
✓ Backup enabled for 'myvm'
  Schedule: Daily at 2:00 AM UTC
  Retention: 90 days
  Compression: Enabled
  Verification: Enabled
  Next Backup: Tomorrow at 2:00 AM
```

### Create Manual Backup

```bash
# Create immediate backup
azlin backup create myvm --name "pre-upgrade-backup"

# Create with description
azlin backup create myvm \
  --name "before-migration" \
  --description "Backup before datacenter migration" \
  --tags "migration,critical"
```

### Restore from Backup

```bash
# List available backups
azlin backup list myvm

# Restore to new VM
azlin backup restore myvm \
  --backup-id "backup-20251203-020000" \
  --target myvm-restored

# Restore to specific point in time
azlin backup restore myvm \
  --timestamp "2025-12-03T02:00:00Z" \
  --target myvm-restored
```

## Backup Management

### Backup Schedules

Configure automated backup schedules:

```bash
# Hourly backups (24-hour retention)
azlin backup enable myvm \
  --schedule hourly \
  --retention 1d

# Daily backups (30-day retention)
azlin backup enable myvm \
  --schedule daily \
  --retention 30d

# Weekly backups (12-week retention)
azlin backup enable myvm \
  --schedule weekly \
  --day Sunday \
  --retention 12w

# Monthly backups (12-month retention)
azlin backup enable myvm \
  --schedule monthly \
  --day 1 \
  --retention 12m

# Custom cron schedule
azlin backup enable myvm \
  --schedule "0 */6 * * *"  # Every 6 hours
  --retention 7d
```

### Retention Policies

```bash
# Configure GFS (Grandfather-Father-Son) retention
azlin backup retention myvm \
  --daily 7 \
  --weekly 4 \
  --monthly 12 \
  --yearly 7

# Retention output
Retention Policy: myvm

Daily Backups:    Keep 7 days
Weekly Backups:   Keep 4 weeks  (Sundays)
Monthly Backups:  Keep 12 months (1st of month)
Yearly Backups:   Keep 7 years   (January 1st)

Estimated Storage: 450 GB
Estimated Cost: $22.50/month
```

### Backup Verification

Automatically verify backup integrity:

```bash
# Enable verification
azlin backup verify enable myvm \
  --schedule weekly \
  --test-restore

# Manual verification
azlin backup verify myvm --backup-id "backup-20251203-020000"

# Verification output
Backup Verification: backup-20251203-020000

✓ Snapshot integrity check passed
✓ Data consistency check passed
✓ Metadata validation passed
✓ Test restore successful (3.2 minutes)

Verification Status: PASSED
Backup is restorable
```

## Disaster Recovery

### DR Plan Configuration

Create and manage DR plans:

```bash
# Create DR plan
azlin dr create-plan production-app \
  --vms vm-web-01,vm-db-01,vm-cache-01 \
  --target-region westus \
  --rto 1h \
  --rpo 15m

# DR Plan output
DR Plan: production-app

Primary Region: eastus
DR Region: westus

Protected VMs:
  - vm-web-01 (web server)
  - vm-db-01 (database)
  - vm-cache-01 (redis cache)

Recovery Objectives:
  RTO (Recovery Time Objective): 1 hour
  RPO (Recovery Point Objective): 15 minutes

Failover Order:
  1. vm-cache-01 (no dependencies)
  2. vm-db-01 (depends on cache)
  3. vm-web-01 (depends on database)

Estimated Recovery Time: 45 minutes
```

### DR Testing

Test disaster recovery without affecting production:

```bash
# Run DR test
azlin dr test production-app

# DR Test output
DR Test: production-app
Mode: Isolated Test Environment

[Step 1/5] Creating isolated VNet... ✓ (30s)
[Step 2/5] Restoring VM snapshots...  ✓ (3.2m)
  - vm-cache-01-test
  - vm-db-01-test
  - vm-web-01-test
[Step 3/5] Configuring networking... ✓ (45s)
[Step 4/5] Starting VMs... ✓ (2.1m)
[Step 5/5] Running health checks... ✓ (1.5m)

DR Test Complete (7.8 minutes)

Results:
  ✓ All VMs started successfully
  ✓ Network connectivity verified
  ✓ Application health checks passed
  ✓ Data integrity verified

Test Environment Available:
  Web: https://test-vm-web-01.westus.cloudapp.azure.com
  Duration: 4 hours (auto-cleanup)

Production environment unaffected.
```

### Automated DR Testing

Schedule regular DR tests:

```bash
# Enable monthly DR testing
azlin dr test-schedule production-app \
  --schedule monthly \
  --day 15 \
  --report-to ops@example.com

# DR Test Schedule output
DR Test Schedule: production-app

Frequency: Monthly (15th of each month)
Time: 2:00 AM UTC
Duration: 4 hours
Auto-Cleanup: Enabled

Notifications:
  - ops@example.com (test results)
  - slack: #dr-testing

Next Test: December 15, 2025 at 2:00 AM
```

## Cross-Region Backup Replication

### Configure Replication

Replicate backups to secondary region for DR:

```bash
# Enable cross-region replication
azlin backup replicate enable myvm \
  --target-region westus \
  --replicate-schedule daily

# Replication output
Cross-Region Backup Replication: myvm

Source Region: eastus
Target Region: westus

Replication Schedule: Daily
Bandwidth: Standard (async)
Encryption: Enabled

Status: Active
Last Replication: 2 hours ago
Next Replication: Tomorrow at 3:00 AM
```

### Monitor Replication

```bash
# Check replication status
azlin backup replicate status myvm

# Replication status output
Backup Replication Status: myvm

Source: eastus
Target: westus

Recent Replications:
  2025-12-03 03:00 ✓ Success (450 GB in 25 minutes)
  2025-12-02 03:00 ✓ Success (448 GB in 24 minutes)
  2025-12-01 03:00 ✓ Success (445 GB in 26 minutes)

Current Status:
  Replication Lag: 3 hours
  Data Replicated: 97%
  Transfer Rate: 320 Mbps

Health: ✓ Healthy
```

## Recovery Operations

### Point-in-Time Recovery

Restore VM to specific point in time:

```bash
# Show available recovery points
azlin backup recovery-points myvm

# Recovery points output
Recovery Points: myvm

Latest: 2025-12-03 02:00:00 (2 hours ago)

Daily Recovery Points (Last 30 days):
  2025-12-03 02:00:00  450 GB  ✓ Verified
  2025-12-02 02:00:00  448 GB  ✓ Verified
  2025-12-01 02:00:00  445 GB  ✓ Verified
  ...

Weekly Recovery Points (Last 12 weeks):
  2025-11-24 02:00:00  430 GB  ✓ Verified
  2025-11-17 02:00:00  425 GB  ✓ Verified
  ...

Total Recovery Points: 47
Oldest: 2024-09-03 02:00:00 (3 months ago)
```

```bash
# Restore to specific point
azlin backup restore myvm \
  --recovery-point "2025-12-02 02:00:00" \
  --target myvm-restored \
  --region westus
```

### Granular File Recovery

Restore individual files without full VM restore:

```bash
# Browse backup contents
azlin backup browse myvm \
  --backup-id "backup-20251203-020000" \
  --path /var/www

# Restore specific files
azlin backup restore-files myvm \
  --backup-id "backup-20251203-020000" \
  --files "/var/www/config.php,/etc/nginx/nginx.conf" \
  --target-path ./restored-files/
```

### Database-Consistent Recovery

For database VMs, ensure transactional consistency:

```bash
# Create application-consistent backup
azlin backup create myvm \
  --app-consistent \
  --quiesce database

# Restore with consistency check
azlin backup restore myvm \
  --backup-id "backup-20251203-020000" \
  --verify-consistency \
  --target myvm-db-restored
```

## Compliance & Reporting

### Backup Compliance

Generate compliance reports:

```bash
# Check backup compliance
azlin backup compliance-check

# Compliance report output
Backup Compliance Report
Generated: 2025-12-03 14:30:00

Overall Compliance: 95% ✓

VMs with Compliant Backups (28/30):
  ✓ All production VMs backed up daily
  ✓ All backups verified weekly
  ✓ Retention policies enforced
  ✓ DR testing completed monthly

Non-Compliant VMs (2/30):
  ⚠ vm-dev-temp-01: No backups configured
  ⚠ vm-test-old-02: Backup > 7 days old

Recommendations:
  1. Enable backups for vm-dev-temp-01
  2. Investigate vm-test-old-02 backup failures
  3. Consider enabling cross-region replication for tier-1 VMs
```

### Audit Logs

Track all backup and recovery operations:

```bash
# View backup audit log
azlin backup audit-log --last 30d

# Audit log output
Backup Audit Log (Last 30 days)

2025-12-03 02:00:15  BACKUP_CREATED    myvm         backup-20251203-020000
2025-12-03 02:25:30  BACKUP_VERIFIED   myvm         backup-20251203-020000
2025-12-02 14:30:00  RESTORE_STARTED   myvm         → myvm-test
2025-12-02 14:37:15  RESTORE_COMPLETED myvm         → myvm-test (7.2 min)
2025-12-01 03:00:00  REPLICATION_START myvm         eastus → westus
2025-12-01 03:25:00  REPLICATION_DONE  myvm         450 GB replicated

Total Events: 234
Backups Created: 90
Restorations: 5
Replications: 30
```

## Integration & Automation

### Backup Automation API

```python
from azlin.modules.backup_manager import BackupManager

# Enable automated backups
backup_mgr = BackupManager(vm_name="myvm")
backup_mgr.enable_automated_backup(
    schedule="daily",
    retention_days=30,
    compression=True,
    verification=True
)

# Create backup
backup_id = backup_mgr.create_backup(
    name="manual-backup",
    tags=["important", "pre-upgrade"]
)

# Restore backup
backup_mgr.restore_backup(
    backup_id=backup_id,
    target_vm="myvm-restored",
    region="westus"
)

# Verify backup
result = backup_mgr.verify_backup(backup_id)
print(f"Verification: {result.status}")
```

### DR Testing API

```python
from azlin.modules.dr_testing import DRTester

# Create DR test
dr_tester = DRTester(plan_name="production-app")
test_result = dr_tester.run_dr_test(
    isolated=True,
    duration_hours=4,
    cleanup_after=True
)

# Check test results
print(f"Recovery Time: {test_result.recovery_time}")
print(f"Health Status: {test_result.health_status}")
print(f"Test Passed: {test_result.passed}")
```

## Best Practices

1. **3-2-1 Backup Rule**
   - 3 copies of data
   - 2 different storage types
   - 1 off-site/off-region copy

2. **Test Restores Regularly**
   - Monthly restore tests minimum
   - Verify data integrity
   - Document restore procedures

3. **Implement Retention Policies**
   - Follow GFS (Grandfather-Father-Son)
   - Balance cost vs. compliance
   - Automate old backup cleanup

4. **Enable Verification**
   - Automatic backup verification
   - Weekly consistency checks
   - Alert on verification failures

5. **Plan for DR**
   - Document DR procedures
   - Test DR plans quarterly
   - Keep runbooks updated
   - Define clear RTO/RPO objectives

6. **Monitor Backup Health**
   - Track backup success rates
   - Alert on backup failures
   - Review backup reports monthly

## Troubleshooting

### Backup Failures

**Problem**: Backup creation failing

**Solution**:
```bash
# Check backup logs
azlin backup logs myvm --last 24h

# Verify disk space
azlin backup check-space myvm

# Test manual backup
azlin backup create myvm --name test-backup --verbose
```

### Slow Restores

**Problem**: Restore taking longer than expected

**Solution**:
```bash
# Use lower-latency target region
azlin backup restore myvm --target-region eastus

# Restore to higher-tier storage
azlin backup restore myvm --storage-tier Premium

# Restore with parallel transfer
azlin backup restore myvm --parallel-threads 8
```

### Replication Lag

**Problem**: Cross-region replication falling behind

**Solution**:
```bash
# Check replication bandwidth
azlin backup replicate status myvm --verbose

# Increase replication priority
azlin backup replicate configure myvm --priority high

# Force immediate replication
azlin backup replicate now myvm
```

## See Also

- [Snapshots Management](../snapshots/index.md)
- [Multi-Region Orchestration](./multi-region.md)
- [VM Lifecycle Automation](../vm-lifecycle/automation.md)
- [Storage Management](../storage/index.md)

---

*Documentation last updated: 2025-12-03*
