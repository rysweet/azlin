# Backup & Disaster Recovery - Architecture Specification

## Overview

This specification defines the architecture for comprehensive automated backup and disaster recovery capabilities for azlin-managed VMs. The system extends the existing `SnapshotManager` with scheduled backup automation, cross-region replication, backup verification, and disaster recovery testing.

## Explicit User Requirements (CANNOT BE OPTIMIZED AWAY)

1. **Automated backup scheduling** - Daily/weekly/monthly retention policies with automatic execution
2. **Point-in-time recovery** - Restore to any backup with <15 min RTO (Recovery Time Objective)
3. **Cross-region backup replication** - Replicate backups to secondary region for geo-redundancy
4. **DR testing automation** - Automated DR drills with 99.9% success rate target
5. **Backup verification and integrity checks** - Verify all backups are restorable and uncorrupted

## Technical Decisions

- **Foundation**: Extend existing `SnapshotManager` module (proven, working code)
- **Storage**: Azure Snapshots with cross-region replication via Azure CLI
- **Scheduling**: Manual trigger via CLI with schedule metadata in VM tags (consistent with SnapshotManager design)
- **Verification**: Test-restore to temporary disks without VM disruption
- **DR Testing**: Automated restore tests in parallel region
- **Metadata Storage**: VM tags + local SQLite for replication tracking (no external database)

## Design Philosophy Compliance

Following azlin's core principles:

1. **Ruthless Simplicity**: Extend proven SnapshotManager, no new frameworks
2. **Brick Philosophy**: Self-contained modules with clear contracts
3. **Zero-BS Implementation**: Every function must work or not exist
4. **Security-First**: No credentials in code, input validation throughout
5. **Fail-Fast**: Prerequisite checking upfront, clear error messages

## Module Architecture

### 1. Backup Manager Module (`src/azlin/modules/backup_manager.py`)

**Purpose**: Automated backup scheduling with retention policies

**Brick Specification**:
```python
"""Automated backup management with retention policies.

Philosophy:
- Single responsibility: backup automation and retention
- Extends SnapshotManager for core snapshot operations
- Self-contained and regeneratable

Public API (the "studs"):
    BackupManager: Main backup orchestration class
    BackupSchedule: Schedule configuration dataclass
    BackupInfo: Backup metadata dataclass
    configure_backup(): Configure backup schedule for VM
    trigger_backup(): Execute scheduled backup operation
    list_backups(): List all backups with retention info
"""

@dataclass
class BackupSchedule:
    """Backup schedule configuration stored in VM tags."""
    enabled: bool
    daily_retention: int      # Days to keep daily backups
    weekly_retention: int     # Weeks to keep weekly backups
    monthly_retention: int    # Months to keep monthly backups
    last_daily: datetime | None = None
    last_weekly: datetime | None = None
    last_monthly: datetime | None = None
    cross_region_enabled: bool = False
    target_region: str | None = None

@dataclass
class BackupInfo:
    """Backup metadata with retention tier."""
    snapshot_name: str
    vm_name: str
    resource_group: str
    creation_time: datetime
    retention_tier: str  # daily, weekly, monthly
    replicated: bool = False
    verified: bool = False
    size_gb: int | None = None

class BackupManager:
    """Automated backup management with tiered retention."""

    BACKUP_SCHEDULE_TAG = "azlin:backup-schedule"

    @classmethod
    def configure_backup(
        cls,
        vm_name: str,
        resource_group: str,
        daily_retention: int = 7,
        weekly_retention: int = 4,
        monthly_retention: int = 12,
        cross_region: bool = False,
        target_region: str | None = None,
    ) -> None:
        """Configure backup schedule with retention policies."""

    @classmethod
    def trigger_backup(
        cls,
        vm_name: str,
        resource_group: str,
        force_tier: str | None = None,
    ) -> BackupInfo:
        """Execute scheduled backup with appropriate retention tier.

        Determines tier based on schedule:
        - Daily: Every day
        - Weekly: First backup of each week (Sunday)
        - Monthly: First backup of each month (1st day)
        """

    @classmethod
    def list_backups(
        cls,
        vm_name: str,
        resource_group: str,
        tier: str | None = None,
    ) -> list[BackupInfo]:
        """List all backups with retention tier information."""

    @classmethod
    def cleanup_expired_backups(
        cls,
        vm_name: str,
        resource_group: str,
    ) -> dict[str, int]:
        """Remove backups beyond retention policies.

        Returns:
            Dictionary with counts: {"daily": N, "weekly": M, "monthly": K}
        """
```

**Implementation Notes**:
- Uses SnapshotManager for actual snapshot creation
- Stores BackupSchedule in VM tags (consistent with SnapshotManager pattern)
- Backup naming: `{vm_name}-backup-{tier}-{timestamp}`
- Retention logic:
  - Daily: Keep last N days
  - Weekly: Keep first backup of each week for N weeks
  - Monthly: Keep first backup of each month for N months
- Tags each snapshot with retention tier for tracking
- Cleanup runs automatically after each backup

**Integration with SnapshotManager**:
```python
# BackupManager delegates to SnapshotManager for core operations
from azlin.modules.snapshot_manager import SnapshotManager

class BackupManager:
    @classmethod
    def _create_backup_snapshot(cls, vm_name: str, resource_group: str, tier: str) -> str:
        """Create backup snapshot using SnapshotManager."""
        snapshot_info = SnapshotManager.create_snapshot(vm_name, resource_group)
        # Tag snapshot with backup tier
        cls._tag_snapshot_as_backup(snapshot_info.name, resource_group, tier)
        return snapshot_info.name
```

### 2. Backup Replication Module (`src/azlin/modules/backup_replication.py`)

**Purpose**: Cross-region backup replication for geo-redundancy

**Brick Specification**:
```python
"""Cross-region backup replication.

Philosophy:
- Single responsibility: geo-redundancy only
- Standard library + Azure CLI
- Self-contained and regeneratable

Public API (the "studs"):
    ReplicationManager: Main replication class
    ReplicationJob: Replication job tracking
    replicate_backup(): Replicate single backup to target region
    replicate_all_pending(): Replicate all unreplicated backups
    check_replication_status(): Verify replication completion
"""

@dataclass
class ReplicationJob:
    """Tracks cross-region replication job."""
    source_snapshot: str
    target_snapshot: str
    source_region: str
    target_region: str
    source_resource_group: str
    target_resource_group: str
    status: str  # pending, in_progress, completed, failed
    started_at: datetime
    completed_at: datetime | None = None
    error_message: str | None = None

class ReplicationManager:
    """Cross-region backup replication manager."""

    def __init__(
        self,
        storage_path: Path = Path.home() / ".azlin" / "replication.db",
    ):
        """Initialize replication manager with SQLite tracking."""

    def replicate_backup(
        self,
        snapshot_name: str,
        source_resource_group: str,
        target_region: str,
        target_resource_group: str | None = None,
    ) -> ReplicationJob:
        """Replicate backup to target region.

        Process:
        1. Create snapshot copy in target region
        2. Track job in SQLite
        3. Verify replication completion
        4. Update backup metadata
        """

    def replicate_all_pending(
        self,
        vm_name: str,
        source_resource_group: str,
        target_region: str,
        max_parallel: int = 3,
    ) -> list[ReplicationJob]:
        """Replicate all unreplicated backups in parallel."""

    def check_replication_status(
        self,
        job_id: int,
    ) -> ReplicationJob:
        """Check status of replication job."""

    def list_replication_jobs(
        self,
        vm_name: str | None = None,
        status: str | None = None,
    ) -> list[ReplicationJob]:
        """List replication jobs with optional filters."""
```

**Database Schema**:
```sql
CREATE TABLE replication_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_snapshot TEXT NOT NULL,
    target_snapshot TEXT NOT NULL,
    source_region TEXT NOT NULL,
    target_region TEXT NOT NULL,
    source_resource_group TEXT NOT NULL,
    target_resource_group TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at DATETIME NOT NULL,
    completed_at DATETIME,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_snapshot ON replication_jobs(source_snapshot);
CREATE INDEX idx_status ON replication_jobs(status);
CREATE INDEX idx_target_region ON replication_jobs(target_region);
```

**Implementation Notes**:
- Uses Azure CLI for cross-region snapshot copy
- Tracks jobs in SQLite for status monitoring
- Parallel replication with configurable concurrency
- Automatic retry on transient failures (3 attempts)
- Target resource group defaults to source RG if not specified
- Replication typically takes 5-15 minutes per snapshot

**Azure CLI Commands**:
```bash
# Copy snapshot to another region
az snapshot create \
  --name {target_snapshot_name} \
  --resource-group {target_resource_group} \
  --location {target_region} \
  --source {source_snapshot_id} \
  --output json
```

### 3. Backup Verification Module (`src/azlin/modules/backup_verification.py`)

**Purpose**: Verify backup integrity and restorability

**Brick Specification**:
```python
"""Backup verification and integrity checking.

Philosophy:
- Single responsibility: verification only
- Non-disruptive testing (temporary disks)
- Self-contained and regeneratable

Public API (the "studs"):
    VerificationManager: Main verification class
    VerificationResult: Verification outcome dataclass
    verify_backup(): Verify single backup
    verify_all_backups(): Verify all unverified backups
    get_verification_report(): Generate verification report
"""

@dataclass
class VerificationResult:
    """Backup verification result."""
    backup_name: str
    vm_name: str
    verified_at: datetime
    success: bool
    disk_readable: bool
    size_matches: bool
    test_disk_created: bool
    test_disk_deleted: bool
    error_message: str | None = None
    verification_time_seconds: float = 0.0

class VerificationManager:
    """Backup verification manager."""

    def __init__(
        self,
        storage_path: Path = Path.home() / ".azlin" / "verification.db",
    ):
        """Initialize verification manager with SQLite tracking."""

    def verify_backup(
        self,
        snapshot_name: str,
        resource_group: str,
    ) -> VerificationResult:
        """Verify backup by creating temporary test disk.

        Process:
        1. Create test disk from snapshot
        2. Verify disk properties (size, status)
        3. Delete test disk immediately
        4. Record verification result
        """

    def verify_all_backups(
        self,
        vm_name: str,
        resource_group: str,
        max_parallel: int = 2,
    ) -> list[VerificationResult]:
        """Verify all unverified backups."""

    def get_verification_report(
        self,
        vm_name: str | None = None,
        days: int = 7,
    ) -> dict[str, Any]:
        """Generate verification report.

        Returns:
            {
                "total_verified": int,
                "success_rate": float,
                "failures": list[VerificationResult],
                "last_verified": datetime,
            }
        """
```

**Database Schema**:
```sql
CREATE TABLE verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    backup_name TEXT NOT NULL,
    vm_name TEXT NOT NULL,
    verified_at DATETIME NOT NULL,
    success BOOLEAN NOT NULL,
    disk_readable BOOLEAN,
    size_matches BOOLEAN,
    test_disk_created BOOLEAN,
    test_disk_deleted BOOLEAN,
    error_message TEXT,
    verification_time_seconds REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_backup_name ON verifications(backup_name);
CREATE INDEX idx_vm_name ON verifications(vm_name);
CREATE INDEX idx_verified_at ON verifications(verified_at);
CREATE INDEX idx_success ON verifications(success);
```

**Implementation Notes**:
- Non-disruptive: Uses temporary test disks, not production VMs
- Quick verification (1-2 minutes per backup)
- Verifies: disk creation succeeds, size matches, disk is readable
- Automatic cleanup: test disks deleted immediately after verification
- Parallel verification with conservative concurrency (2 max)
- Scheduled verification: daily for recent backups, weekly for older

### 4. DR Testing Module (`src/azlin/modules/dr_testing.py`)

**Purpose**: Automated disaster recovery testing

**Brick Specification**:
```python
"""Disaster recovery testing automation.

Philosophy:
- Single responsibility: DR testing only
- Automated restore validation
- Self-contained and regeneratable

Public API (the "studs"):
    DRTestManager: Main DR testing class
    DRTestResult: Test result dataclass
    DRTestConfig: Test configuration
    run_dr_test(): Execute complete DR test
    run_scheduled_tests(): Run all scheduled DR tests
    get_test_history(): Retrieve test results
"""

@dataclass
class DRTestConfig:
    """DR test configuration."""
    vm_name: str
    backup_name: str
    source_resource_group: str
    test_region: str
    test_resource_group: str
    verify_boot: bool = True
    verify_connectivity: bool = True
    cleanup_after_test: bool = True

@dataclass
class DRTestResult:
    """DR test execution result."""
    test_id: int
    vm_name: str
    backup_name: str
    test_region: str
    started_at: datetime
    completed_at: datetime | None = None
    success: bool = False
    restore_succeeded: bool = False
    boot_succeeded: bool = False
    connectivity_succeeded: bool = False
    cleanup_succeeded: bool = False
    rto_seconds: float | None = None  # Recovery Time Objective
    error_message: str | None = None

class DRTestManager:
    """Disaster recovery testing manager."""

    def __init__(
        self,
        storage_path: Path = Path.home() / ".azlin" / "dr_tests.db",
    ):
        """Initialize DR test manager."""

    def run_dr_test(
        self,
        config: DRTestConfig,
    ) -> DRTestResult:
        """Execute complete DR test.

        Process:
        1. Restore backup to test VM in target region
        2. Verify VM boots successfully
        3. Verify SSH connectivity
        4. Measure RTO (Recovery Time Objective)
        5. Clean up test resources
        6. Record test results
        """

    def run_scheduled_tests(
        self,
        resource_group: str,
    ) -> list[DRTestResult]:
        """Run DR tests for all VMs with DR enabled.

        Schedule: Weekly DR test for each VM
        """

    def get_test_history(
        self,
        vm_name: str | None = None,
        days: int = 30,
    ) -> list[DRTestResult]:
        """Retrieve DR test history."""

    def get_success_rate(
        self,
        vm_name: str | None = None,
        days: int = 30,
    ) -> float:
        """Calculate DR test success rate."""
```

**Database Schema**:
```sql
CREATE TABLE dr_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vm_name TEXT NOT NULL,
    backup_name TEXT NOT NULL,
    test_region TEXT NOT NULL,
    started_at DATETIME NOT NULL,
    completed_at DATETIME,
    success BOOLEAN,
    restore_succeeded BOOLEAN,
    boot_succeeded BOOLEAN,
    connectivity_succeeded BOOLEAN,
    cleanup_succeeded BOOLEAN,
    rto_seconds REAL,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_vm_name_test ON dr_tests(vm_name);
CREATE INDEX idx_started_at ON dr_tests(started_at);
CREATE INDEX idx_success_test ON dr_tests(success);
```

**Implementation Notes**:
- Full restore test: Creates actual VM from backup in test region
- RTO measurement: Time from restore start to VM ready (target: <15 min)
- Automated verification: Boot check + SSH connectivity
- Automatic cleanup: Test VM and resources deleted after test
- Weekly scheduling for each VM with DR enabled
- Success rate target: 99.9% (allow 1 failure per 1000 tests)
- Test isolation: Uses separate resource group to avoid production impact

## CLI Command Specifications

### Backup Configuration Commands

```bash
# Configure automated backup schedule
azlin backup configure <vm-name> \
  --daily-retention 7 \
  --weekly-retention 4 \
  --monthly-retention 12 \
  --cross-region \
  --target-region westus2

# Disable backup for VM
azlin backup disable <vm-name>

# Show backup configuration
azlin backup config-show <vm-name>
```

### Backup Execution Commands

```bash
# Trigger backup manually (determines tier automatically)
azlin backup trigger <vm-name>

# Force specific retention tier
azlin backup trigger <vm-name> --tier daily|weekly|monthly

# List all backups for VM
azlin backup list <vm-name>

# List backups by tier
azlin backup list <vm-name> --tier weekly

# Restore from backup
azlin backup restore <vm-name> --backup <backup-name>

# Point-in-time restore (select from available backups)
azlin backup restore <vm-name> --interactive
```

### Cross-Region Replication Commands

```bash
# Replicate specific backup
azlin backup replicate <backup-name> --target-region westus2

# Replicate all unreplicated backups
azlin backup replicate-all <vm-name> --target-region westus2

# Check replication status
azlin backup replication-status <vm-name>

# List replication jobs
azlin backup replication-jobs [--status pending|completed|failed]
```

### Verification Commands

```bash
# Verify specific backup
azlin backup verify <backup-name>

# Verify all backups for VM
azlin backup verify-all <vm-name>

# Show verification report
azlin backup verification-report [--vm <name>] [--days 7]
```

### DR Testing Commands

```bash
# Run DR test for VM
azlin dr test <vm-name> \
  --backup <backup-name> \
  --test-region westus2

# Run all scheduled DR tests
azlin dr test-all

# Show DR test history
azlin dr test-history <vm-name> [--days 30]

# Show DR success rate
azlin dr success-rate [--vm <name>] [--days 30]
```

## Integration with Existing SnapshotManager

### Relationship

```
SnapshotManager (existing)
    ↓ uses
BackupManager (new)
    ↓ uses
┌─────────────────────────────────┐
│ ReplicationManager              │
│ VerificationManager             │
│ DRTestManager                   │
└─────────────────────────────────┘
```

### Backward Compatibility

- Existing `azlin snapshot` commands remain unchanged
- SnapshotManager continues to work independently
- BackupManager adds new `azlin backup` commands
- Both systems can coexist on same VM
- Backups are special snapshots with additional metadata tags

### Code Reuse Strategy

```python
# BackupManager extends SnapshotManager functionality
class BackupManager:
    # Reuse snapshot creation
    @classmethod
    def _create_backup_snapshot(cls, vm_name, resource_group, tier):
        snapshot = SnapshotManager.create_snapshot(vm_name, resource_group)
        # Add backup-specific tags
        cls._tag_as_backup(snapshot.name, tier)
        return snapshot

    # Reuse snapshot listing
    @classmethod
    def list_backups(cls, vm_name, resource_group):
        all_snapshots = SnapshotManager.list_snapshots(vm_name, resource_group)
        # Filter to backups only
        return [s for s in all_snapshots if cls._is_backup(s)]

    # Reuse snapshot deletion
    @classmethod
    def _delete_backup(cls, backup_name, resource_group):
        SnapshotManager.delete_snapshot(backup_name, resource_group)
```

## Implementation Phases

### Phase 1: Backup Manager (Week 1)

**Deliverables**:
- `backup_manager.py` module implementation
- CLI commands: `configure`, `trigger`, `list`, `restore`
- Unit tests for retention logic
- Integration tests with SnapshotManager

**Success Criteria**:
- Can configure backup schedules via VM tags
- Daily/weekly/monthly retention works correctly
- Expired backups cleaned up automatically
- Restore from backup succeeds

**Testing**:
- Create VM, configure backup schedule
- Trigger multiple backups over simulated days/weeks
- Verify correct retention tier assignment
- Verify cleanup removes expired backups only
- Test restore from each retention tier

### Phase 2: Cross-Region Replication (Week 2)

**Deliverables**:
- `backup_replication.py` module implementation
- SQLite replication tracking database
- CLI commands: `replicate`, `replicate-all`, `replication-status`
- Unit tests for replication logic
- Integration tests with Azure regions

**Success Criteria**:
- Backups replicate to target region successfully
- Replication status tracked accurately
- Failed replications retry automatically
- Parallel replication works without conflicts

**Testing**:
- Configure backup with cross-region enabled
- Verify backups replicate to target region
- Test parallel replication of multiple backups
- Verify replication job tracking
- Test failure scenarios and retries

### Phase 3: Backup Verification (Week 3)

**Deliverables**:
- `backup_verification.py` module implementation
- SQLite verification tracking database
- CLI commands: `verify`, `verify-all`, `verification-report`
- Unit tests for verification logic
- Integration tests with test disk creation

**Success Criteria**:
- Test disks created from snapshots successfully
- Verification completes without disrupting production
- Failed verifications reported clearly
- Verification report shows success rate

**Testing**:
- Verify multiple backups in sequence
- Verify test disk creation and cleanup
- Test verification of corrupted/invalid snapshots
- Verify parallel verification works correctly
- Check verification report accuracy

### Phase 4: DR Testing Automation (Week 4)

**Deliverables**:
- `dr_testing.py` module implementation
- SQLite DR test tracking database
- CLI commands: `test`, `test-all`, `test-history`, `success-rate`
- Unit tests for DR test orchestration
- Integration tests with full VM restore

**Success Criteria**:
- DR tests create VM from backup in test region
- RTO measured accurately (<15 min target)
- Boot and connectivity verified
- Test resources cleaned up automatically
- Success rate tracking works

**Testing**:
- Run DR test for single VM
- Verify RTO measurement accuracy
- Test boot and connectivity verification
- Verify cleanup of test resources
- Run scheduled tests for multiple VMs
- Check success rate calculation (target: 99.9%)

### Phase 5: Security Review & Documentation (Week 5)

**Deliverables**:
- Security review by security agent
- User documentation for all features
- Operator runbooks for DR procedures
- Performance benchmarks and tuning
- Final integration testing

**Success Criteria**:
- Security review passes with no critical issues
- All features documented with examples
- DR runbooks complete and tested
- Performance meets targets (RTO <15 min)
- End-to-end integration tests pass

**Security Review Checklist**:
- Input validation on all parameters
- No credentials in code or logs
- Proper error handling without leaking sensitive info
- Resource cleanup prevents orphaned resources
- Cross-region access properly authenticated
- SQLite databases secured with appropriate permissions

## Performance Targets

| Operation | Target | Measurement |
|-----------|--------|-------------|
| Backup creation | <5 min | Time to create snapshot |
| Cross-region replication | <15 min | Time to copy snapshot |
| Backup verification | <2 min | Time for test disk create/delete |
| DR test (full restore) | <15 min RTO | Time from start to VM ready |
| Backup listing | <5 sec | Time to list all backups |
| Cleanup expired backups | <10 min | Time to delete all expired |

## Cost Estimation

**Storage Costs** (per VM):
- Daily backups (7 days @ 128GB): ~$45/month
- Weekly backups (4 weeks @ 128GB): ~$26/month
- Monthly backups (12 months @ 128GB): ~$77/month
- Cross-region replication (2x storage): 2x above costs
- **Total per VM**: ~$150-300/month depending on replication

**Compute Costs** (per VM):
- DR tests (4 hours/month test VM runtime): ~$10/month
- Verification test disks (minimal, deleted quickly): ~$2/month
- **Total per VM**: ~$12/month

**Overall Cost**: ~$160-310/month per VM with full backup/DR

**Cost Optimization Options**:
- Reduce retention periods
- Disable cross-region replication for non-critical VMs
- Use cheaper storage tiers for older backups
- Reduce DR test frequency

## Monitoring & Alerting Integration

The backup/DR system integrates with the monitoring system (WS1 - Issue #438) for:

**Backup Alerts**:
- Backup failures (snapshot creation failed)
- Retention policy violations (backups not cleaned up)
- Replication failures (cross-region copy failed)

**DR Alerts**:
- DR test failures (restore/boot/connectivity failed)
- RTO threshold exceeded (restore took >15 min)
- Success rate below target (<99.9%)

**Verification Alerts**:
- Verification failures (backup not restorable)
- Verification not run (backups unverified for >7 days)

**Alert Configuration**:
```yaml
# ~/.azlin/alerts.yaml
backup_failure:
  enabled: true
  severity: high
  channels: [slack, email]

dr_test_failure:
  enabled: true
  severity: critical
  channels: [slack, email, webhook]

rto_exceeded:
  enabled: true
  severity: high
  threshold_minutes: 15
  channels: [slack]
```

## Security Considerations

1. **Authentication**: All operations use Azure CLI authentication (delegated)
2. **Authorization**: Requires appropriate Azure RBAC roles:
   - Snapshot creation: `Contributor` or `Disk Backup Reader`
   - Cross-region replication: `Contributor` in both regions
   - DR testing: `Virtual Machine Contributor`
3. **Data Protection**:
   - Snapshots inherit VM disk encryption
   - Cross-region replication maintains encryption
   - No backup data stored locally (only metadata)
4. **Access Control**:
   - SQLite databases have restricted permissions (600)
   - VM tags readable only by Azure account owner
5. **Audit Trail**:
   - All operations logged to SQLite with timestamps
   - Failed operations logged with error details
   - Success/failure metrics tracked for compliance

## Disaster Recovery Runbook

### Scenario 1: VM Corruption - Point-in-Time Restore

**Trigger**: VM disk corrupted, need restore to last known good state

**Steps**:
1. `azlin backup list <vm-name>` - List available backups
2. `azlin backup restore <vm-name> --backup <backup-name>` - Restore selected backup
3. Verify VM boots and operates correctly
4. **RTO Target**: <15 minutes

**Automation**: Can be scripted for automated rollback

### Scenario 2: Region Outage - Cross-Region Failover

**Trigger**: Primary region unavailable, fail over to secondary region

**Steps**:
1. `azlin backup replication-status <vm-name>` - Verify recent backup replicated
2. `azlin dr test <vm-name> --backup <backup-name> --test-region <secondary-region>` - Restore in secondary region
3. Update DNS/load balancer to point to new VM
4. **RTO Target**: <15 minutes (restore) + DNS propagation

**Automation**: Can trigger automatically based on region health checks

### Scenario 3: Data Loss - Restore to Specific Point in Time

**Trigger**: Accidental data deletion, need restore to before deletion

**Steps**:
1. `azlin backup list <vm-name> --tier all` - Find backup before deletion
2. `azlin backup verify <backup-name>` - Verify backup integrity
3. `azlin backup restore <vm-name> --backup <backup-name>` - Restore
4. **RTO Target**: <15 minutes

### Scenario 4: Compliance Testing - Quarterly DR Drill

**Trigger**: Scheduled compliance requirement for DR testing

**Steps**:
1. `azlin dr test-all` - Run DR tests for all VMs
2. `azlin dr success-rate --days 90` - Verify 99.9% success rate
3. `azlin backup verification-report --days 90` - Verify all backups tested
4. Generate compliance report with test results

**Automation**: Can be scheduled via cron for automatic quarterly execution

## Future Enhancements (Not in Scope)

1. **Incremental Backups**: Azure snapshots are already incremental at Azure level
2. **Application-Consistent Backups**: Requires guest agent integration
3. **Backup Encryption with Customer-Managed Keys**: Azure handles encryption
4. **Backup to External Storage**: AWS S3, Google Cloud Storage integration
5. **Multi-VM Coordinated Backups**: Backup multiple VMs atomically
6. **Backup Policies via Templates**: Define backup policies in templates
7. **Cost Optimization Recommendations**: Analyze backup usage patterns
8. **Compliance Reporting Dashboard**: Visual compliance dashboards

## Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Backup success rate | >99% | Successful backups / total attempts |
| Replication success rate | >95% | Successful replications / total attempts |
| Verification success rate | >99% | Verified backups / total backups |
| DR test success rate | >99.9% | Successful DR tests / total tests |
| RTO (Recovery Time Objective) | <15 min | Median time for full restore |
| RPO (Recovery Point Objective) | <24 hours | Max time between backups |

## Conclusion

This backup and disaster recovery system provides comprehensive protection for azlin-managed VMs while maintaining the project's core philosophy of ruthless simplicity. By extending the proven SnapshotManager foundation and using VM tags + local SQLite for metadata, we avoid external dependencies while delivering enterprise-grade backup and DR capabilities.

The phased implementation approach ensures each component is fully tested and working before moving to the next, with clear success criteria and rollback capabilities at each phase.
