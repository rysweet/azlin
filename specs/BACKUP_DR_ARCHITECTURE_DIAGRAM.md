# Backup & Disaster Recovery - Architecture Diagram

## System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          azlin CLI (Orchestrator)                        │
│                                                                          │
│  ┌────────────────────────────┐  ┌─────────────────────────────────┐   │
│  │  azlin backup commands     │  │  azlin dr commands              │   │
│  │  - configure               │  │  - test                         │   │
│  │  - trigger                 │  │  - test-all                     │   │
│  │  - list/restore            │  │  - test-history                 │   │
│  │  - replicate               │  │  - success-rate                 │   │
│  │  - verify                  │  │                                 │   │
│  └────────────┬───────────────┘  └────────────┬────────────────────┘   │
│               │                               │                         │
└───────────────┼───────────────────────────────┼─────────────────────────┘
                │                               │
                │                               │
┌───────────────▼───────────────────────────────▼─────────────────────────┐
│                     Backup & DR Module Layer                             │
│                                                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │ BackupManager    │  │ ReplicationMgr   │  │ VerificationManager  │  │
│  │                  │  │                  │  │                      │  │
│  │ • Schedule       │  │ • Cross-region   │  │ • Test disk verify   │  │
│  │ • Retention      │  │ • Job tracking   │  │ • Integrity check    │  │
│  │ • Cleanup        │  │ • Parallel copy  │  │ • Results logging    │  │
│  └────────┬─────────┘  └────────┬─────────┘  └────────┬─────────────┘  │
│           │                     │                      │                │
│  ┌────────▼───────────────────────────────────────────▼─────────────┐  │
│  │                    DRTestManager                                  │  │
│  │                                                                   │  │
│  │  • Full restore test in parallel region                          │  │
│  │  • RTO measurement                                               │  │
│  │  • Boot/connectivity validation                                  │  │
│  │  • Automated cleanup                                             │  │
│  └───────────────────────────────┬───────────────────────────────────┘  │
│                                  │                                      │
└──────────────────────────────────┼──────────────────────────────────────┘
                                   │
                                   │
┌──────────────────────────────────▼──────────────────────────────────────┐
│                   Existing SnapshotManager (Foundation)                 │
│                                                                          │
│  • create_snapshot()  - Core snapshot creation                          │
│  • list_snapshots()   - Snapshot enumeration                            │
│  • delete_snapshot()  - Cleanup operations                              │
│  • restore_snapshot() - VM restore from snapshot                        │
│                                                                          │
└──────────────────────────────────┬──────────────────────────────────────┘
                                   │
                                   │
┌──────────────────────────────────▼──────────────────────────────────────┐
│                     Storage & Metadata Layer                             │
│                                                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────┐  │
│  │ VM Tags          │  │ SQLite DBs       │  │ Azure Snapshots      │  │
│  │                  │  │                  │  │                      │  │
│  │ • azlin:backup-  │  │ • replication.db │  │ • Primary region     │  │
│  │   schedule       │  │ • verification.db│  │ • Secondary region   │  │
│  │ • Retention cfg  │  │ • dr_tests.db    │  │ • Tagged by tier     │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────┘  │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagrams

### Backup Creation Flow

```
┌──────────┐
│   User   │
└────┬─────┘
     │ azlin backup trigger myvm
     │
     ▼
┌──────────────────┐
│ BackupManager    │
│ .trigger_backup()│
└────┬─────────────┘
     │ 1. Read backup schedule from VM tags
     │ 2. Determine retention tier (daily/weekly/monthly)
     │
     ▼
┌──────────────────┐
│ SnapshotManager  │
│ .create_snapshot()│
└────┬─────────────┘
     │ 3. Create Azure snapshot
     │
     ▼
┌──────────────────┐
│ BackupManager    │
│ .tag_as_backup() │
└────┬─────────────┘
     │ 4. Tag snapshot with tier
     │ 5. Update last_backup time in VM tags
     │
     ▼
┌──────────────────┐
│ BackupManager    │
│ .cleanup_expired()│
└────┬─────────────┘
     │ 6. Delete backups beyond retention
     │
     ▼
┌──────────────────┐
│ Result           │
│ BackupInfo       │
└──────────────────┘
```

### Cross-Region Replication Flow

```
┌──────────┐
│   User   │
└────┬─────┘
     │ azlin backup replicate-all myvm --target-region westus2
     │
     ▼
┌──────────────────────┐
│ ReplicationManager   │
│ .replicate_all_      │
│  pending()           │
└────┬─────────────────┘
     │ 1. List unreplicated backups
     │
     ▼
┌──────────────────────┐
│ Parallel Processing  │
│ (3 workers)          │
└────┬─────────────────┘
     │ 2. For each backup:
     │
     ▼
┌──────────────────────┐
│ Azure CLI            │
│ az snapshot create   │
└────┬─────────────────┘
     │ 3. Copy snapshot to target region
     │ 4. Track job in replication.db
     │
     ▼
┌──────────────────────┐
│ ReplicationManager   │
│ .check_status()      │
└────┬─────────────────┘
     │ 5. Poll for completion
     │ 6. Update job status in DB
     │ 7. Mark backup as replicated
     │
     ▼
┌──────────────────────┐
│ Result               │
│ List[ReplicationJob] │
└──────────────────────┘
```

### Backup Verification Flow

```
┌──────────┐
│   User   │
└────┬─────┘
     │ azlin backup verify-all myvm
     │
     ▼
┌──────────────────────┐
│ VerificationManager  │
│ .verify_all_backups()│
└────┬─────────────────┘
     │ 1. List unverified backups
     │
     ▼
┌──────────────────────┐
│ Parallel Processing  │
│ (2 workers)          │
└────┬─────────────────┘
     │ 2. For each backup:
     │
     ▼
┌──────────────────────┐
│ Azure CLI            │
│ az disk create       │
└────┬─────────────────┘
     │ 3. Create test disk from snapshot
     │
     ▼
┌──────────────────────┐
│ VerificationManager  │
│ .validate_disk()     │
└────┬─────────────────┘
     │ 4. Check disk properties (size, status)
     │
     ▼
┌──────────────────────┐
│ Azure CLI            │
│ az disk delete       │
└────┬─────────────────┘
     │ 5. Delete test disk immediately
     │
     ▼
┌──────────────────────┐
│ VerificationManager  │
│ .record_result()     │
└────┬─────────────────┘
     │ 6. Save verification result to DB
     │
     ▼
┌──────────────────────┐
│ Result               │
│ List[VerificationRes]│
└──────────────────────┘
```

### DR Test Flow

```
┌──────────┐
│   User   │
└────┬─────┘
     │ azlin dr test myvm --backup backup-20251201 --test-region westus2
     │
     ▼
┌──────────────────────┐
│ DRTestManager        │
│ .run_dr_test()       │
└────┬─────────────────┘
     │ 1. Validate backup exists & replicated
     │ 2. Start RTO timer
     │
     ▼
┌──────────────────────┐
│ SnapshotManager      │
│ .restore_snapshot()  │
└────┬─────────────────┘
     │ 3. Create VM from backup in test region
     │ 4. Create test resource group
     │
     ▼
┌──────────────────────┐
│ DRTestManager        │
│ .verify_boot()       │
└────┬─────────────────┘
     │ 5. Wait for VM running status
     │ 6. Check boot succeeded
     │
     ▼
┌──────────────────────┐
│ DRTestManager        │
│ .verify_connectivity()│
└────┬─────────────────┘
     │ 7. Test SSH connectivity
     │ 8. Stop RTO timer
     │
     ▼
┌──────────────────────┐
│ DRTestManager        │
│ .cleanup_test_vm()   │
└────┬─────────────────┘
     │ 9. Delete test VM & resources
     │
     ▼
┌──────────────────────┐
│ DRTestManager        │
│ .record_result()     │
└────┬─────────────────┘
     │ 10. Save test result to DB
     │     (success, RTO, failure details)
     │
     ▼
┌──────────────────────┐
│ Result               │
│ DRTestResult         │
└──────────────────────┘
```

## Module Dependency Graph

```
                    ┌─────────────────┐
                    │   azlin CLI     │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
              ▼              ▼              ▼
    ┌─────────────┐  ┌──────────────┐  ┌────────────┐
    │BackupManager│  │ Replication  │  │Verification│
    │             │  │   Manager    │  │  Manager   │
    └──────┬──────┘  └──────┬───────┘  └─────┬──────┘
           │                │                 │
           └────────────────┼─────────────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │  DRTestManager  │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │SnapshotManager  │
                   │   (existing)    │
                   └────────┬────────┘
                            │
                            ▼
                   ┌─────────────────┐
                   │   Azure CLI     │
                   │   + Azure API   │
                   └─────────────────┘
```

## Database Schema Overview

### replication.db

```sql
CREATE TABLE replication_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_snapshot TEXT NOT NULL,
    target_snapshot TEXT NOT NULL,
    source_region TEXT NOT NULL,
    target_region TEXT NOT NULL,
    status TEXT NOT NULL,  -- pending, in_progress, completed, failed
    started_at DATETIME NOT NULL,
    completed_at DATETIME,
    error_message TEXT
);

CREATE INDEX idx_snapshot ON replication_jobs(source_snapshot);
CREATE INDEX idx_status ON replication_jobs(status);
```

### verification.db

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
    verification_time_seconds REAL
);

CREATE INDEX idx_backup_name ON verifications(backup_name);
CREATE INDEX idx_verified_at ON verifications(verified_at);
```

### dr_tests.db

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
    rto_seconds REAL,  -- Recovery Time Objective measurement
    error_message TEXT
);

CREATE INDEX idx_vm_name_test ON dr_tests(vm_name);
CREATE INDEX idx_started_at ON dr_tests(started_at);
```

## State Transition Diagrams

### Backup State Transitions

```
                     ┌───────────┐
                     │   Start   │
                     └─────┬─────┘
                           │
                           ▼
                 ┌──────────────────┐
                 │ Schedule Check   │
                 │ (from VM tags)   │
                 └────┬──────┬──────┘
                      │      │
         Is due? ─────┘      └───── Not due (skip)
                      │
                      ▼
            ┌──────────────────┐
            │ Create Snapshot  │
            │ (via SnapshotMgr)│
            └────┬──────────────┘
                 │
                 ▼
        ┌──────────────────────┐
        │ Determine Tier       │
        │ (daily/weekly/monthly)│
        └────┬─────────────────┘
             │
             ▼
    ┌──────────────────────┐
    │ Tag with Metadata    │
    │ (tier, timestamp)    │
    └────┬─────────────────┘
         │
         ▼
┌──────────────────────────┐
│ Update VM Tags           │
│ (last_backup_time)       │
└────┬─────────────────────┘
     │
     ▼
┌──────────────────────────┐
│ Cleanup Expired Backups  │
│ (retention policy)       │
└────┬─────────────────────┘
     │
     ▼
┌──────────────────────────┐
│   Backup Complete        │
└──────────────────────────┘
```

### Replication State Transitions

```
┌──────────┐
│  Pending │ ────────────────┐
└────┬─────┘                 │
     │                       │
     │ Start replication     │
     │                       │
     ▼                       │
┌──────────────┐             │
│ In Progress  │             │ Retry on transient failure
└────┬───┬─────┘             │
     │   │                   │
     │   └── Transient ──────┘
     │       Failure
     │
     │ Success / Permanent Failure
     │
     ├────────────┬────────────┐
     │            │            │
     ▼            ▼            ▼
┌──────────┐ ┌──────────┐ ┌──────────┐
│Completed │ │  Failed  │ │  Failed  │
│          │ │(transient)│ │(permanent)│
└──────────┘ └──────────┘ └──────────┘
```

## Security Layers

```
┌─────────────────────────────────────────────────────┐
│             Application Security Layer               │
│                                                      │
│  • Input Validation (whitelist-based)              │
│  • SQL Injection Prevention (parameterized queries) │
│  • Error Sanitization (sensitive data removed)      │
│  • Rate Limiting (operation throttling)             │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│           Authorization & Authentication             │
│                                                      │
│  • Azure CLI Delegation (no credential storage)     │
│  • RBAC Validation (check permissions)              │
│  • Session Token Validation (verify token valid)    │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│              Data Protection Layer                   │
│                                                      │
│  • Snapshot Encryption (Azure-managed)              │
│  • Metadata Encryption (SQLite fields)              │
│  • File Permissions (600 on databases)              │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│             Audit & Compliance Layer                 │
│                                                      │
│  • Operation Logging (all actions tracked)          │
│  • Compliance Reporting (backup/restore/test logs)  │
│  • Secure Audit Log (restricted permissions)        │
└─────────────────────────────────────────────────────┘
```

## Integration Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    azlin Ecosystem                          │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│  │ Monitoring   │  │  Snapshot    │  │  VM Lifecycle   │  │
│  │ System       │  │  Manager     │  │  Manager        │  │
│  │ (WS1-#438)   │  │  (existing)  │  │  (WS2-#435)     │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬────────┘  │
│         │                 │                    │           │
│         │  Alerts         │  Core Snapshots    │  VM Info  │
│         │                 │                    │           │
│  ┌──────▼─────────────────▼────────────────────▼────────┐  │
│  │          Backup & Disaster Recovery System          │  │
│  │                                                      │  │
│  │  • Extends SnapshotManager for backup automation    │  │
│  │  • Sends alerts to Monitoring System                │  │
│  │  • Uses VM Lifecycle for VM status                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

---

**Visual Guide Version**: 1.0
**Last Updated**: 2025-12-01
**Related Documents**: BACKUP_DR_SPEC.md, BACKUP_DR_SUMMARY.md
