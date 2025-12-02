# Storage Management Enhancement Specification

**Issue**: #442
**Workstream**: WS8
**Status**: Design Phase
**Date**: 2025-12-01

## Executive Summary

Ahoy! This specification extends azlin's existing storage management capabilities with quota management, performance tier optimization, orphaned resource cleanup, cost optimization, and multi-VM NFS performance tuning. The design follows the brick philosophy, extending the battle-tested `StorageManager` foundation with new self-contained modules.

**Success Metrics**:
- 30% cost reduction through tier optimization and orphaned resource cleanup
- 20% NFS performance improvement through intelligent tuning
- Zero manual quota failures through proactive management

## Existing Foundation

azlin already has a solid storage foundation:

**Modules**:
- `storage_manager.py` - Azure Files NFS storage account management (862 lines)
- `storage_key_manager.py` - Storage key retrieval and management
- `snapshot_manager.py` - VM snapshot management with scheduling (851 lines)
- `quota_manager.py` - VM quota tracking (287 lines)

**CLI Commands**:
- `azlin storage create` - Create storage accounts (Premium/Standard)
- `azlin storage list` - List storage accounts
- `azlin storage status` - Show usage and cost
- `azlin storage delete` - Delete storage
- `azlin storage mount vm` - Mount NFS on VM
- `azlin storage mount local` - Mount SMB locally

**Data Models**:
- `StorageInfo` - Storage account information
- `StorageStatus` - Usage, connected VMs, cost
- `QuotaInfo` - Quota tracking (repurpose for storage quotas)

## Architecture Overview

### Design Philosophy

**Extend, Don't Replace**: Build on `StorageManager` following these principles:

1. **Brick Architecture**: Each new capability is a self-contained module
2. **Standard Library First**: Use subprocess + Azure CLI for operations
3. **Zero-BS Implementation**: Every function works or doesn't exist
4. **Clear Contracts**: Public APIs via `__all__`, dataclass models
5. **Fail Fast**: Validate inputs, explicit error messages

### Module Dependencies

```
┌─────────────────────────────────────────────────────────────┐
│                   CLI Commands Layer                        │
│  azlin storage quota | tier | cleanup | cost | nfs-tune    │
└─────────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  New Storage Modules                        │
│  QuotaManager | TierOptimizer | OrphanedDetector |         │
│  CostAdvisor | NFSTuner                                     │
└─────────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                 Existing Foundation                         │
│  StorageManager (create, list, status, delete)             │
│  StorageKeyManager (key retrieval)                          │
│  SnapshotManager (snapshot lifecycle)                       │
└─────────────────────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     Azure CLI                               │
│  az storage account | az disk | az snapshot                │
└─────────────────────────────────────────────────────────────┘
```

## Module 1: Storage Quota Manager

### Purpose

Track and enforce storage quotas per VM, team (resource group), or project (subscription).

### Contract

**Public API**:
```python
class StorageQuotaManager:
    @classmethod
    def set_quota(
        cls,
        scope: str,  # "vm", "team", "project"
        name: str,   # VM name, RG name, or subscription ID
        quota_gb: int,
        resource_group: str | None = None
    ) -> QuotaConfig

    @classmethod
    def get_quota(
        cls,
        scope: str,
        name: str,
        resource_group: str | None = None
    ) -> QuotaStatus

    @classmethod
    def check_quota(
        cls,
        scope: str,
        name: str,
        requested_gb: int,
        resource_group: str | None = None
    ) -> QuotaCheckResult

    @classmethod
    def list_quotas(
        cls,
        resource_group: str | None = None
    ) -> list[QuotaStatus]
```

**Data Models**:
```python
@dataclass
class QuotaConfig:
    """Storage quota configuration."""
    scope: str           # "vm", "team", "project"
    name: str           # Identifier
    quota_gb: int       # Total quota
    created: datetime
    last_updated: datetime

@dataclass
class QuotaStatus:
    """Current quota usage status."""
    config: QuotaConfig
    used_gb: float
    available_gb: float
    utilization_percent: float
    storage_accounts: list[str]  # Contributing storage accounts
    disks: list[str]             # Contributing managed disks
    snapshots: list[str]         # Contributing snapshots

@dataclass
class QuotaCheckResult:
    """Result of quota availability check."""
    available: bool
    current_usage_gb: float
    quota_gb: int
    requested_gb: int
    remaining_after_gb: float
    message: str
```

**Dependencies**:
- `StorageManager` - Get storage account sizes
- Azure CLI `az disk list` - List managed disks and sizes
- Azure CLI `az snapshot list` - List snapshots and sizes
- `ConfigManager` - Store quota configurations

**Implementation Notes**:

1. **Quota Storage**: Store quotas in `~/.azlin/quotas.json`:
   ```json
   {
     "vm": {
       "my-dev-vm": {"quota_gb": 500, "created": "2025-12-01T..."}
     },
     "team": {
       "azlin-dev-rg": {"quota_gb": 2000, "created": "2025-12-01T..."}
     },
     "project": {
       "sub-12345": {"quota_gb": 10000, "created": "2025-12-01T..."}
     }
   }
   ```

2. **Usage Calculation**:
   - VM scope: Sum storage accounts mounted on VM + VM disks + VM snapshots
   - Team scope: Sum all storage/disks/snapshots in resource group
   - Project scope: Sum all storage/disks/snapshots in subscription

3. **Enforcement**: Check quotas before:
   - `azlin storage create`
   - `azlin new` (VM creation)
   - Snapshot creation

### CLI Commands

```bash
# Set quotas
azlin storage quota set --scope vm --name my-dev-vm --quota 500
azlin storage quota set --scope team --name azlin-dev-rg --quota 2000
azlin storage quota set --scope project --quota 10000

# Check quota status
azlin storage quota status --scope vm --name my-dev-vm
azlin storage quota status --scope team
azlin storage quota status --scope project

# List all quotas
azlin storage quota list
azlin storage quota list --scope team

# Remove quota
azlin storage quota remove --scope vm --name my-dev-vm
```

**Output Example**:
```
Storage Quota Status: my-dev-vm (VM)
================================
Quota:        500 GB
Used:         387 GB (77.4%)
Available:    113 GB

Storage Breakdown:
  Storage Accounts:
    - myteam-shared: 100 GB

  Managed Disks:
    - my-dev-vm_OsDisk: 128 GB
    - my-dev-vm_datadisk_0: 256 GB

  Snapshots:
    - my-dev-vm-snapshot-20251201: 3 GB
```

## Module 2: Storage Tier Optimizer

### Purpose

Analyze usage patterns and recommend/apply optimal storage tiers (Premium vs Standard) for cost vs performance.

### Contract

**Public API**:
```python
class StorageTierOptimizer:
    @classmethod
    def analyze_storage(
        cls,
        storage_name: str,
        resource_group: str,
        days: int = 30
    ) -> TierAnalysis

    @classmethod
    def recommend_tier(
        cls,
        storage_name: str,
        resource_group: str
    ) -> TierRecommendation

    @classmethod
    def migrate_tier(
        cls,
        storage_name: str,
        resource_group: str,
        target_tier: str,
        confirm: bool = False
    ) -> TierMigrationResult

    @classmethod
    def audit_all_storage(
        cls,
        resource_group: str
    ) -> list[TierRecommendation]
```

**Data Models**:
```python
@dataclass
class TierAnalysis:
    """Storage tier usage analysis."""
    storage_name: str
    current_tier: str
    size_gb: int
    usage_pattern: str      # "high", "medium", "low"
    connected_vms: int
    avg_operations_per_day: int  # Estimated from metrics
    current_cost_per_month: float

@dataclass
class TierRecommendation:
    """Tier optimization recommendation."""
    storage_name: str
    current_tier: str
    recommended_tier: str
    reason: str
    current_cost_per_month: float
    potential_cost_per_month: float
    annual_savings: float
    performance_impact: str  # "none", "minor", "significant"
    confidence: str          # "high", "medium", "low"

@dataclass
class TierMigrationResult:
    """Result of tier migration operation."""
    storage_name: str
    old_tier: str
    new_tier: str
    success: bool
    new_storage_name: str | None  # Migration creates new storage
    migration_steps: list[str]
    errors: list[str]
```

**Dependencies**:
- `StorageManager` - Get current tier and status
- Azure CLI `az storage account` - Tier information
- Azure Monitor metrics (optional) - Usage patterns

**Implementation Notes**:

1. **Usage Pattern Heuristics** (without Azure Monitor metrics):
   - **High**: >3 connected VMs OR Premium tier requested
   - **Medium**: 1-3 connected VMs
   - **Low**: 0 connected VMs OR backup/archive storage

2. **Tier Recommendations**:
   - Premium → Standard: Low usage + high cost (>$15/mo savings)
   - Standard → Premium: High usage + performance complaints
   - Consider: Connected VMs, utilization, cost impact

3. **Migration Process** (Azure limitation: can't change tier in-place):
   - Create new storage account with target tier
   - Copy data using `az storage copy` (for files) or `azcopy`
   - Update VM mount configurations
   - Delete old storage after verification
   - **IMPORTANT**: Requires downtime or temporary dual-mount

4. **Cost Calculations**:
   - Premium: $0.1536/GB/month
   - Standard: $0.04/GB/month
   - Minimum savings threshold: $10/month or 20% reduction

### CLI Commands

```bash
# Analyze specific storage
azlin storage tier analyze myteam-shared

# Get recommendation
azlin storage tier recommend myteam-shared

# Audit all storage in RG
azlin storage tier audit
azlin storage tier audit --resource-group azlin-rg

# Migrate tier (requires confirmation)
azlin storage tier migrate myteam-shared --tier Standard
azlin storage tier migrate myteam-shared --tier Standard --confirm
```

**Output Example**:
```
Storage Tier Analysis: myteam-shared
====================================
Current Tier:      Premium
Size:              100 GB
Connected VMs:     1
Usage Pattern:     Low
Current Cost:      $15.36/month

Recommendation:    Migrate to Standard
Potential Cost:    $4.00/month
Annual Savings:    $136.32
Performance Impact: Minor (single VM workload)
Confidence:        High

Reason: Storage is Premium tier but has only 1 connected VM with
low utilization. Standard tier would provide adequate performance
at 74% cost reduction.

To migrate:
  azlin storage tier migrate myteam-shared --tier Standard --confirm
```

## Module 3: Orphaned Resource Detector

### Purpose

Detect and clean up orphaned managed disks, snapshots, and storage accounts that are no longer attached to VMs.

### Contract

**Public API**:
```python
class OrphanedResourceDetector:
    @classmethod
    def scan_orphaned_disks(
        cls,
        resource_group: str,
        min_age_days: int = 7
    ) -> list[OrphanedDisk]

    @classmethod
    def scan_orphaned_snapshots(
        cls,
        resource_group: str,
        min_age_days: int = 30
    ) -> list[OrphanedSnapshot]

    @classmethod
    def scan_orphaned_storage(
        cls,
        resource_group: str,
        min_age_days: int = 30
    ) -> list[OrphanedStorage]

    @classmethod
    def scan_all(
        cls,
        resource_group: str
    ) -> OrphanedResourceReport

    @classmethod
    def cleanup_orphaned(
        cls,
        resource_group: str,
        resource_type: str,  # "disk", "snapshot", "storage", "all"
        min_age_days: int,
        dry_run: bool = True
    ) -> CleanupResult
```

**Data Models**:
```python
@dataclass
class OrphanedDisk:
    """Orphaned managed disk information."""
    name: str
    resource_group: str
    size_gb: int
    tier: str
    created: datetime
    age_days: int
    last_attached_vm: str | None
    monthly_cost: float
    reason: str  # Why considered orphaned

@dataclass
class OrphanedSnapshot:
    """Orphaned snapshot information."""
    name: str
    resource_group: str
    size_gb: int
    created: datetime
    age_days: int
    source_vm: str | None
    monthly_cost: float
    reason: str

@dataclass
class OrphanedStorage:
    """Orphaned storage account information."""
    name: str
    resource_group: str
    size_gb: int
    tier: str
    created: datetime
    age_days: int
    connected_vms: list[str]
    monthly_cost: float
    reason: str

@dataclass
class OrphanedResourceReport:
    """Complete orphaned resources report."""
    disks: list[OrphanedDisk]
    snapshots: list[OrphanedSnapshot]
    storage_accounts: list[OrphanedStorage]
    total_cost_per_month: float
    total_size_gb: int
    scan_date: datetime

@dataclass
class CleanupResult:
    """Cleanup operation results."""
    deleted_disks: list[str]
    deleted_snapshots: list[str]
    deleted_storage: list[str]
    total_size_freed_gb: int
    total_cost_saved_per_month: float
    errors: list[str]
    dry_run: bool
```

**Dependencies**:
- Azure CLI `az disk list` - List managed disks
- Azure CLI `az snapshot list` - List snapshots
- `StorageManager` - List storage accounts
- `SnapshotManager` - Snapshot information
- `ConfigManager` - Track VM-storage associations

**Implementation Notes**:

1. **Orphaned Disk Detection**:
   - No `managedBy` property (not attached to VM)
   - Age > min_age_days (default: 7 days)
   - Exclude: Disks with `azlin:keep` tag

2. **Orphaned Snapshot Detection**:
   - Source VM no longer exists
   - Age > min_age_days (default: 30 days)
   - Exclude: Snapshots with `azlin:keep` tag
   - Exclude: Snapshots within retention policy (from `SnapshotManager`)

3. **Orphaned Storage Detection**:
   - No connected VMs (empty `connected_vms` list)
   - Age > min_age_days (default: 30 days)
   - Exclude: Storage with `azlin:keep` tag
   - Exclude: Storage marked as shared in config

4. **Safety Mechanisms**:
   - Default dry_run=True (show what would be deleted)
   - Minimum age requirements prevent accidental deletion
   - Respect `azlin:keep` tags for protected resources
   - Require explicit confirmation for deletion

5. **Cost Calculations**:
   - Managed disks: Based on tier (Premium/Standard) and size
   - Snapshots: ~$0.05/GB/month
   - Storage accounts: From `StorageManager.COST_PER_GB`

### CLI Commands

```bash
# Scan for orphaned resources
azlin storage cleanup scan
azlin storage cleanup scan --resource-group azlin-rg
azlin storage cleanup scan --type disk
azlin storage cleanup scan --type snapshot
azlin storage cleanup scan --min-age-days 30

# Cleanup (dry run by default)
azlin storage cleanup --type all
azlin storage cleanup --type disk --min-age-days 7
azlin storage cleanup --type snapshot --min-age-days 60

# Actually delete (requires --confirm)
azlin storage cleanup --type all --confirm
azlin storage cleanup --type disk --confirm --min-age-days 14
```

**Output Example**:
```
Orphaned Resources Scan: azlin-dev-rg
=====================================
Scan Date: 2025-12-01 15:30:00

Orphaned Managed Disks (3):
  1. old-vm-OsDisk_1
     Size: 128 GB | Age: 45 days | Cost: $9.83/mo
     Reason: VM deleted, disk unattached for 45 days

  2. test-datadisk_0
     Size: 256 GB | Age: 12 days | Cost: $19.66/mo
     Reason: No longer attached to any VM

  3. backup-disk-old
     Size: 512 GB | Age: 90 days | Cost: $20.48/mo
     Reason: Standard disk unattached for 90 days

Orphaned Snapshots (5):
  1. deleted-vm-snapshot-20251101
     Size: 128 GB | Age: 30 days | Cost: $6.40/mo
     Reason: Source VM no longer exists

  [... 4 more snapshots ...]

Orphaned Storage Accounts (1):
  1. oldprojectstorage
     Size: 100 GB | Age: 60 days | Cost: $15.36/mo
     Reason: No VMs connected for 60 days

Summary:
  Total Resources: 9
  Total Size:      1,324 GB
  Monthly Cost:    $121.43
  Annual Savings:  $1,457.16 (if cleaned)

To delete these resources:
  azlin storage cleanup --type all --confirm
```

## Module 4: Cost Advisor

### Purpose

Provide cost analysis and optimization recommendations across all storage resources.

### Contract

**Public API**:
```python
class StorageCostAdvisor:
    @classmethod
    def analyze_costs(
        cls,
        resource_group: str,
        period_days: int = 30
    ) -> CostAnalysis

    @classmethod
    def get_recommendations(
        cls,
        resource_group: str
    ) -> list[CostRecommendation]

    @classmethod
    def estimate_savings(
        cls,
        resource_group: str,
        recommendations: list[CostRecommendation] | None = None
    ) -> SavingsEstimate

    @classmethod
    def generate_report(
        cls,
        resource_group: str,
        output_format: str = "text"  # "text", "json", "csv"
    ) -> str
```

**Data Models**:
```python
@dataclass
class CostAnalysis:
    """Complete storage cost analysis."""
    resource_group: str
    period_days: int
    total_cost: float
    cost_breakdown: CostBreakdown
    trends: CostTrends
    analysis_date: datetime

@dataclass
class CostBreakdown:
    """Cost breakdown by resource type."""
    storage_accounts: float
    managed_disks: float
    snapshots: float
    orphaned_resources: float

    def total(self) -> float:
        return (self.storage_accounts + self.managed_disks +
                self.snapshots + self.orphaned_resources)

@dataclass
class CostTrends:
    """Cost trend analysis."""
    daily_average: float
    monthly_projection: float
    month_over_month_change_percent: float | None

@dataclass
class CostRecommendation:
    """Cost optimization recommendation."""
    category: str  # "tier", "orphaned", "snapshot-retention", "resize"
    resource_name: str
    resource_type: str
    action: str
    current_cost_per_month: float
    potential_cost_per_month: float
    monthly_savings: float
    annual_savings: float
    effort: str  # "low", "medium", "high"
    risk: str   # "low", "medium", "high"
    priority: int  # 1-5 (1=highest)

@dataclass
class SavingsEstimate:
    """Total savings potential."""
    total_monthly_savings: float
    total_annual_savings: float
    recommendations_count: int
    savings_by_category: dict[str, float]
    confidence: str  # "high", "medium", "low"
```

**Dependencies**:
- `StorageManager` - Storage account costs
- `OrphanedResourceDetector` - Orphaned resource costs
- `StorageTierOptimizer` - Tier optimization savings
- `SnapshotManager` - Snapshot costs
- Azure CLI - Managed disk costs

**Implementation Notes**:

1. **Cost Calculation Sources**:
   - Storage accounts: `StorageManager.COST_PER_GB`
   - Managed disks: Based on tier (Premium ~$0.15/GB, Standard ~$0.04/GB)
   - Snapshots: ~$0.05/GB/month
   - Orphaned resources: From `OrphanedResourceDetector`

2. **Recommendation Categories**:
   - **Tier optimization**: Downgrade underutilized Premium to Standard
   - **Orphaned cleanup**: Delete unused resources
   - **Snapshot retention**: Reduce retention periods
   - **Storage resize**: Reduce over-provisioned quotas

3. **Priority Calculation**:
   - Priority 1: High savings (>$50/mo), low risk, low effort
   - Priority 2: High savings, medium risk/effort
   - Priority 3: Medium savings (>$20/mo)
   - Priority 4: Low savings but quick wins
   - Priority 5: Low savings, high effort/risk

4. **Reporting Formats**:
   - **Text**: Human-readable console output
   - **JSON**: Machine-readable for automation
   - **CSV**: Spreadsheet import for stakeholder reviews

### CLI Commands

```bash
# Analyze costs
azlin storage cost analyze
azlin storage cost analyze --resource-group azlin-rg
azlin storage cost analyze --period-days 30

# Get recommendations
azlin storage cost recommendations
azlin storage cost recommendations --sort-by savings
azlin storage cost recommendations --min-savings 10

# Estimate total savings
azlin storage cost savings
azlin storage cost savings --apply-recommendations

# Generate reports
azlin storage cost report
azlin storage cost report --format json
azlin storage cost report --format csv --output costs.csv
```

**Output Example**:
```
Storage Cost Analysis: azlin-dev-rg
===================================
Period: Last 30 days
Analysis Date: 2025-12-01

Current Costs:
  Storage Accounts:     $245.76/month
  Managed Disks:        $128.44/month
  Snapshots:            $42.50/month
  Orphaned Resources:   $121.43/month
  ─────────────────────────────────
  Total:                $538.13/month

Cost Optimization Recommendations (8):
  Priority 1: High Impact, Low Risk
    1. Clean up orphaned resources
       Annual Savings: $1,457.16 | Effort: Low | Risk: Low

    2. Downgrade myteam-shared to Standard tier
       Annual Savings: $136.32 | Effort: Medium | Risk: Low

  Priority 2: Medium Impact
    3. Reduce snapshot retention: test-vm (5→2)
       Annual Savings: $76.80 | Effort: Low | Risk: Low

    [... 5 more recommendations ...]

Savings Summary:
  Total Monthly Savings: $157.23
  Total Annual Savings:  $1,886.76
  Potential Cost:        $380.90/month (29% reduction)
  Confidence:            High

To implement:
  1. Review recommendations: azlin storage cost recommendations
  2. Apply cleanup: azlin storage cleanup --type all --confirm
  3. Migrate tiers: azlin storage tier migrate myteam-shared --tier Standard
```

## Module 5: NFS Performance Tuner

### Purpose

Optimize NFS mount parameters for multi-VM scenarios to improve performance by 20%.

### Contract

**Public API**:
```python
class NFSPerformanceTuner:
    @classmethod
    def analyze_performance(
        cls,
        storage_name: str,
        resource_group: str
    ) -> NFSPerformanceAnalysis

    @classmethod
    def get_tuning_recommendations(
        cls,
        storage_name: str,
        resource_group: str,
        workload_type: str = "auto"  # "auto", "read-heavy", "write-heavy", "mixed"
    ) -> NFSTuningRecommendation

    @classmethod
    def apply_tuning(
        cls,
        vm_name: str,
        storage_name: str,
        resource_group: str,
        tuning_profile: str = "recommended"
    ) -> NFSTuningResult

    @classmethod
    def test_performance(
        cls,
        vm_name: str,
        resource_group: str,
        test_type: str = "quick"  # "quick", "full"
    ) -> NFSPerformanceTest
```

**Data Models**:
```python
@dataclass
class NFSPerformanceAnalysis:
    """NFS mount performance analysis."""
    storage_name: str
    connected_vms: list[str]
    current_mount_options: dict[str, str]  # VM -> mount options
    performance_tier: str  # Storage tier (Premium/Standard)
    bottleneck_indicators: list[str]
    optimization_potential: str  # "high", "medium", "low"

@dataclass
class NFSTuningRecommendation:
    """NFS mount tuning recommendations."""
    storage_name: str
    workload_type: str
    recommended_mount_options: str
    expected_improvement_percent: int
    rationale: str
    specific_recommendations: list[str]

@dataclass
class NFSTuningResult:
    """Result of applying NFS tuning."""
    vm_name: str
    storage_name: str
    old_mount_options: str
    new_mount_options: str
    remounted: bool
    performance_change_percent: float | None
    errors: list[str]

@dataclass
class NFSPerformanceTest:
    """NFS performance test results."""
    vm_name: str
    test_type: str
    read_throughput_mbps: float
    write_throughput_mbps: float
    latency_ms: float
    iops: int
    test_duration_seconds: int
```

**Dependencies**:
- `StorageManager` - Storage information
- `NFSMountManager` - Current mount configuration
- SSH access to VMs for:
  - Reading `/etc/fstab` and current mount options
  - Applying new mount options
  - Running performance tests (dd, fio)

**Implementation Notes**:

1. **NFS Mount Options** (Azure Files NFS specific):
   - **Default (baseline)**:
     ```
     vers=4.1,sec=sys,proto=tcp,timeo=600,retrans=2
     ```

   - **Read-heavy workload**:
     ```
     vers=4.1,sec=sys,proto=tcp,timeo=600,retrans=2,
     rsize=1048576,wsize=1048576,hard,
     ac,acregmin=3,acregmax=60,acdirmin=30,acdirmax=60
     ```
     Rationale: Larger read sizes, aggressive attribute caching

   - **Write-heavy workload**:
     ```
     vers=4.1,sec=sys,proto=tcp,timeo=600,retrans=2,
     rsize=1048576,wsize=1048576,hard,noac,async
     ```
     Rationale: Larger write sizes, async writes, no attribute caching

   - **Mixed/balanced workload**:
     ```
     vers=4.1,sec=sys,proto=tcp,timeo=600,retrans=2,
     rsize=1048576,wsize=1048576,hard,
     ac,acregmin=10,acregmax=30
     ```
     Rationale: Moderate caching, large I/O sizes

   - **Multi-VM scenario** (DEFAULT for azlin):
     ```
     vers=4.1,sec=sys,proto=tcp,timeo=600,retrans=2,
     rsize=1048576,wsize=1048576,hard,
     actimeo=1
     ```
     Rationale: Short attribute cache timeout (1s) prevents stale file attributes
     when multiple VMs share storage

2. **Workload Type Detection** (auto mode):
   - Read-heavy: Mostly development environments, code reading
   - Write-heavy: Build/CI environments, log aggregation
   - Mixed: General purpose development
   - Multi-VM: Default when >1 VM connected

3. **Performance Testing**:
   - **Quick test** (30 seconds):
     ```bash
     # Sequential read
     dd if=/home/azureuser/testfile of=/dev/null bs=1M count=1024

     # Sequential write
     dd if=/dev/zero of=/home/azureuser/testfile bs=1M count=1024
     ```

   - **Full test** (5 minutes) using `fio`:
     ```bash
     # Install fio if needed
     # Run comprehensive I/O tests: read, write, random read, random write
     fio --name=nfs_test --directory=/home/azureuser --size=1G \
         --rw=randrw --bs=4k --numjobs=4 --time_based --runtime=300
     ```

4. **Performance Expectations**:
   - **Premium NFS**:
     - Read: Up to 4 GB/s
     - Write: Up to 2 GB/s
     - Latency: <1ms
   - **Standard NFS**:
     - Read: Up to 60 MB/s
     - Write: Up to 60 MB/s
     - Latency: 2-10ms
   - **Optimization gains**: 15-25% improvement from tuning

5. **Safety Mechanisms**:
   - Test mount options before making persistent
   - Keep backup of original `/etc/fstab`
   - Provide rollback capability
   - Warn about potential data consistency issues with aggressive caching

### CLI Commands

```bash
# Analyze NFS performance
azlin storage nfs analyze myteam-shared
azlin storage nfs analyze myteam-shared --vm my-dev-vm

# Get tuning recommendations
azlin storage nfs tune myteam-shared --recommend
azlin storage nfs tune myteam-shared --workload read-heavy --recommend

# Apply tuning
azlin storage nfs tune myteam-shared --vm my-dev-vm
azlin storage nfs tune myteam-shared --vm my-dev-vm --profile read-heavy
azlin storage nfs tune myteam-shared --vm my-dev-vm --custom-options "..."

# Test performance
azlin storage nfs test --vm my-dev-vm
azlin storage nfs test --vm my-dev-vm --type full

# Compare before/after
azlin storage nfs benchmark --vm my-dev-vm --compare
```

**Output Example**:
```
NFS Performance Analysis: myteam-shared
=======================================
Storage Tier:      Premium
Connected VMs:     3 (my-dev-vm, test-vm, build-vm)
Workload Type:     Multi-VM (auto-detected)

Current Mount Options (my-dev-vm):
  vers=4.1,sec=sys,proto=tcp,timeo=600,retrans=2

Issues Detected:
  ⚠ Default mount options in multi-VM scenario
  ⚠ Small read/write buffer sizes (default)
  ⚠ Long attribute cache timeout (60s) may cause stale data

Tuning Recommendations:
  Profile: Multi-VM Optimized
  Options: vers=4.1,sec=sys,proto=tcp,timeo=600,retrans=2,
           rsize=1048576,wsize=1048576,hard,actimeo=1

  Expected Improvement: 15-20%

  Changes:
    ✓ Increase read buffer to 1MB (from 64KB)
    ✓ Increase write buffer to 1MB (from 64KB)
    ✓ Reduce attribute cache timeout to 1s (from 60s)
    ✓ Enable hard mount for reliability

  Rationale:
    - Larger buffers improve throughput for large file operations
    - Short attribute cache prevents stale metadata in multi-VM scenario
    - Hard mount ensures I/O operations complete reliably

To apply tuning:
  azlin storage nfs tune myteam-shared --vm my-dev-vm --profile multi-vm

To test current performance:
  azlin storage nfs test --vm my-dev-vm
```

## CLI Command Structure

### New Commands

```
azlin storage quota
  ├── set       - Set storage quota
  ├── status    - Show quota usage
  ├── list      - List all quotas
  └── remove    - Remove quota

azlin storage tier
  ├── analyze   - Analyze storage tier usage
  ├── recommend - Get tier recommendation
  ├── audit     - Audit all storage tiers
  └── migrate   - Migrate storage tier

azlin storage cleanup
  ├── scan      - Scan for orphaned resources
  └── [default] - Clean up orphaned resources

azlin storage cost
  ├── analyze         - Analyze storage costs
  ├── recommendations - Get cost recommendations
  ├── savings         - Estimate savings
  └── report          - Generate cost report

azlin storage nfs
  ├── analyze   - Analyze NFS performance
  ├── tune      - Apply NFS tuning
  ├── test      - Test NFS performance
  └── benchmark - Compare performance
```

### Integration with Existing Commands

**Extend `azlin storage create`**:
```bash
# Check quota before creation
azlin storage create myteam-shared --size 100
# → Checks team quota automatically
# → Shows warning if approaching limit
# → Fails if quota exceeded
```

**Extend `azlin storage status`**:
```bash
# Show optimization opportunities
azlin storage status myteam-shared
# → Current tier: Premium
# → Recommendation: Consider Standard tier (save $136/year)
# → 0 orphaned snapshots
```

**Extend `azlin new`**:
```bash
# Check VM quota before creation
azlin new my-new-vm
# → Checks VM storage quota
# → Estimates disk size impact
# → Warns if approaching quota
```

## Implementation Phases

### Phase 1: Storage Quota Manager (Week 1)
**Priority**: High (foundation for other features)

**Deliverables**:
- `storage_quota_manager.py` module
- Data models: `QuotaConfig`, `QuotaStatus`, `QuotaCheckResult`
- CLI: `azlin storage quota` command group
- Integration: Add quota checks to `azlin storage create`
- Tests: Unit tests for quota calculation and enforcement

**Success Criteria**:
- Can set quotas at VM/team/project level
- Accurate usage calculation across storage/disks/snapshots
- Quota checks block over-quota operations
- Clear error messages when quota exceeded

### Phase 2: Orphaned Resource Detector (Week 2)
**Priority**: High (immediate cost savings)

**Deliverables**:
- `orphaned_resource_detector.py` module
- Data models: `OrphanedDisk`, `OrphanedSnapshot`, `OrphanedStorage`, `OrphanedResourceReport`
- CLI: `azlin storage cleanup` command group
- Safety: Dry-run default, `azlin:keep` tag support
- Tests: Detection logic, safety mechanisms

**Success Criteria**:
- Accurately detects orphaned disks/snapshots/storage
- Respects safety mechanisms (age, tags)
- Clear reporting with cost impact
- Safe deletion with confirmation

### Phase 3: Cost Advisor (Week 3)
**Priority**: Medium (aggregates other features)

**Deliverables**:
- `storage_cost_advisor.py` module
- Data models: `CostAnalysis`, `CostRecommendation`, `SavingsEstimate`
- CLI: `azlin storage cost` command group
- Integrations: Use `OrphanedResourceDetector`, `StorageTierOptimizer`
- Reports: Text, JSON, CSV formats
- Tests: Cost calculations, recommendations

**Success Criteria**:
- Accurate cost breakdown by resource type
- Actionable recommendations prioritized by impact
- Clear savings estimates
- Multiple report formats

### Phase 4: Storage Tier Optimizer (Week 4)
**Priority**: Medium (complex migration logic)

**Deliverables**:
- `storage_tier_optimizer.py` module
- Data models: `TierAnalysis`, `TierRecommendation`, `TierMigrationResult`
- CLI: `azlin storage tier` command group
- Migration: Safe tier migration workflow
- Tests: Recommendation logic, migration safety

**Success Criteria**:
- Accurate tier recommendations based on usage
- Safe migration workflow (with data copy)
- Clear cost/performance trade-offs
- Rollback capability on failure

### Phase 5: NFS Performance Tuner (Week 5)
**Priority**: Low (optimization, not critical)

**Deliverables**:
- `nfs_performance_tuner.py` module
- Data models: `NFSPerformanceAnalysis`, `NFSTuningRecommendation`, `NFSTuningResult`
- CLI: `azlin storage nfs` command group
- Tuning profiles: Read-heavy, write-heavy, multi-VM
- Performance tests: Quick and full benchmarks
- Tests: Tuning safety, performance validation

**Success Criteria**:
- Safe mount option changes with rollback
- Workload-specific tuning profiles
- Measurable performance improvement (15-20%)
- Performance testing tools integrated

## Testing Strategy

### Unit Tests (60%)

**Per Module**:
- Data model serialization/deserialization
- Input validation
- Cost calculations
- Usage tracking logic
- Recommendation algorithms

**Example** (quota_manager):
```python
class TestStorageQuotaManager:
    def test_set_quota_vm_scope(self):
        # Test VM-level quota setting

    def test_quota_calculation_includes_all_resources(self):
        # Test usage calculation: storage + disks + snapshots

    def test_quota_check_blocks_over_quota_operations(self):
        # Test enforcement

    def test_quota_check_allows_under_quota_operations(self):
        # Test success path
```

### Integration Tests (30%)

**Cross-Module**:
- Quota manager + storage creation
- Orphaned detector + cleanup
- Cost advisor + all modules
- Tier optimizer + storage manager
- NFS tuner + VM manager

**Example** (cleanup integration):
```python
class TestCleanupIntegration:
    def test_cleanup_respects_azlin_keep_tag(self):
        # Create disk, tag it, verify not cleaned

    def test_cleanup_removes_old_orphaned_disk(self):
        # Create unattached disk, verify cleanup

    def test_cleanup_updates_cost_advisor(self):
        # Verify cost advisor reflects cleanup savings
```

### E2E Tests (10%)

**Full Workflows**:
- Create storage → Set quota → Monitor usage → Cleanup
- Create VM → Attach storage → Tune NFS → Test performance
- Audit costs → Apply recommendations → Verify savings

**Example** (cost optimization workflow):
```python
class TestCostOptimizationWorkflow:
    def test_full_cost_optimization_workflow(self):
        # 1. Initial cost analysis
        # 2. Get recommendations
        # 3. Apply tier migration
        # 4. Run cleanup
        # 5. Verify cost reduction
```

## Documentation Requirements

### User Documentation

1. **`docs/storage-management.md`** - User guide:
   - Storage quota management concepts
   - Cost optimization strategies
   - NFS performance tuning guide
   - Cleanup best practices

2. **CLI Help** - Comprehensive help for each command:
   - Examples for common scenarios
   - Warning about destructive operations
   - Links to detailed documentation

3. **Migration Guides**:
   - Tier migration procedure
   - Data safety during migration
   - Rollback procedures

### Developer Documentation

1. **Module READMEs** - For each module:
   - Architecture and design decisions
   - Public API contracts
   - Extension points
   - Testing strategies

2. **`specs/STORAGE_MGMT_SPEC.md`** - This document:
   - Kept updated as implementation evolves
   - Track design decisions and rationale

## Success Metrics

### Primary Metrics

1. **Cost Reduction**: 30% reduction target
   - Measured: Monthly storage costs before/after
   - Tracked: Savings from cleanup + tier optimization
   - Target: $150/month → $105/month (sample project)

2. **NFS Performance**: 20% improvement target
   - Measured: Read/write throughput (MB/s)
   - Tracked: Before/after tuning benchmarks
   - Target: 50 MB/s → 60 MB/s (multi-VM workload)

3. **Quota Management**: Zero quota failures
   - Measured: Storage operations blocked by quota checks
   - Tracked: Proactive warnings vs hard failures
   - Target: 100% of quota violations caught before Azure errors

### Secondary Metrics

1. **Orphaned Resource Detection**:
   - Accuracy: >95% true positives (actually orphaned)
   - Coverage: Detect disks + snapshots + storage
   - Safety: Zero accidental deletions (respect `azlin:keep`)

2. **Recommendation Quality**:
   - Actionability: >80% of recommendations implemented
   - Accuracy: Savings within 10% of estimates
   - Priority: High-priority recommendations deliver >70% of total savings

3. **User Experience**:
   - CLI response time: <5s for analysis commands
   - Help quality: Zero "how do I..." support questions
   - Safety: Zero data loss incidents from cleanup/migration

## Risk Analysis

### High Risk

**Data Loss During Tier Migration**:
- **Mitigation**: Require explicit confirmation, dry-run default, backup verification
- **Rollback**: Keep old storage until new storage validated

**Accidental Deletion of In-Use Resources**:
- **Mitigation**: Multiple safety checks (age, tags, connected VMs), dry-run default
- **Recovery**: Document restoration from Azure soft-delete (if enabled)

### Medium Risk

**NFS Performance Degradation from Bad Tuning**:
- **Mitigation**: Rollback capability, performance testing before/after
- **Recovery**: Restore original mount options from backup

**Quota False Positives Blocking Valid Operations**:
- **Mitigation**: Clear error messages, override mechanism, accurate usage calculation
- **Recovery**: Manual quota adjustment by user

### Low Risk

**Cost Calculation Inaccuracies**:
- **Mitigation**: Document cost assumptions, use conservative estimates
- **Impact**: Low (doesn't affect operations, only advisory)

**Performance Test False Results**:
- **Mitigation**: Run multiple tests, average results, document variance
- **Impact**: Low (doesn't affect operations, only advisory)

## Dependencies

### External

1. **Azure CLI**: All operations use `az` commands
   - Required version: 2.40.0+ (NFS support)
   - Commands: `az storage`, `az disk`, `az snapshot`, `az vm`

2. **SSH Access**: For NFS tuning and performance testing
   - Required: Passwordless SSH to VMs
   - Keys: `~/.ssh/azlin` (existing pattern)

3. **Python Packages**: Standard library only
   - `json`, `subprocess`, `dataclasses`, `datetime`, `pathlib`
   - No new external dependencies

### Internal

1. **Existing Modules**:
   - `StorageManager` - Storage operations
   - `SnapshotManager` - Snapshot tracking
   - `ConfigManager` - Configuration storage
   - `VMManager` - VM information

2. **New Module Interdependencies**:
   - `CostAdvisor` → all other new modules
   - `OrphanedDetector` → `StorageManager`, `SnapshotManager`
   - `TierOptimizer` → `StorageManager`
   - `NFSTuner` → `StorageManager`, VM SSH access

## Appendices

### Appendix A: Azure Storage Costs (as of 2025-12-01)

**Azure Files NFS**:
- Premium: $0.1536/GB/month
- Standard: $0.04/GB/month

**Managed Disks**:
- Premium SSD: $0.1536/GB/month
- Standard SSD: $0.15/GB/month
- Standard HDD: $0.04/GB/month

**Snapshots**:
- Incremental snapshots: $0.05/GB/month (estimated)

**Note**: Actual costs vary by region. These are approximations for eastus2.

### Appendix B: NFS Mount Options Reference

**Standard Options** (from NFSv4.1 spec):
- `vers=4.1` - NFS version
- `proto=tcp` - Protocol (UDP not supported for NFS 4.1)
- `hard/soft` - Hard mount (retry forever) vs soft mount (give up)
- `timeo=N` - Timeout in deciseconds (600 = 60s)
- `retrans=N` - Number of retries before timeout

**I/O Size Options**:
- `rsize=N` - Read buffer size (bytes)
- `wsize=N` - Write buffer size (bytes)
- Default: 65536 (64KB)
- Optimal: 1048576 (1MB) for Azure

**Caching Options**:
- `ac/noac` - Attribute caching on/off
- `actimeo=N` - Attribute cache timeout (seconds)
- `acregmin/acregmax` - Min/max file attribute cache (seconds)
- `acdirmin/acdirmax` - Min/max directory attribute cache (seconds)

**Consistency Options**:
- `async/sync` - Async writes (faster) vs sync writes (safer)
- `nocto` - No close-to-open consistency (faster but less safe)

**Azure-Specific Recommendations**:
- Always use `hard` mount (reliability)
- Use `rsize=1048576,wsize=1048576` (performance)
- Multi-VM: `actimeo=1` (1-second attribute cache prevents stale metadata)
- Single VM: `actimeo=60` (longer cache for performance)

### Appendix C: Workload Type Detection Heuristics

**Read-Heavy** (favor caching):
- Low write operations
- Mostly file reads
- Example: Development environments, code repositories

**Write-Heavy** (favor async writes):
- High write operations
- Frequent file modifications
- Example: Build environments, log aggregation

**Mixed** (balanced):
- Roughly equal read/write
- General-purpose usage
- Example: Standard development workflow

**Multi-VM** (favor consistency):
- Multiple VMs sharing storage
- Risk of stale cached data
- Example: Team-shared development environments

**Auto-Detection Strategy**:
1. Check connected VMs count (>1 = multi-VM)
2. If multi-VM, use multi-VM profile (override workload type)
3. Otherwise, use specified workload type or "mixed" default

### Appendix D: Module File Structure

```
src/azlin/modules/
├── storage_quota_manager.py     # Module 1 (Week 1)
├── orphaned_resource_detector.py # Module 2 (Week 2)
├── storage_cost_advisor.py      # Module 3 (Week 3)
├── storage_tier_optimizer.py    # Module 4 (Week 4)
└── nfs_performance_tuner.py     # Module 5 (Week 5)

src/azlin/commands/
└── storage.py                   # Extend with new command groups

tests/unit/
├── test_storage_quota_manager.py
├── test_orphaned_resource_detector.py
├── test_storage_cost_advisor.py
├── test_storage_tier_optimizer.py
└── test_nfs_performance_tuner.py

tests/integration/
├── test_quota_enforcement.py
├── test_cleanup_workflow.py
├── test_cost_optimization.py
└── test_nfs_tuning.py

tests/e2e/
└── test_storage_management_workflows.py

docs/
└── storage-management.md        # User-facing documentation
```

## Conclusion

This specification provides a comprehensive blueprint fer extending azlin's storage management capabilities. By followin' the brick philosophy and buildin' on the existing `StorageManager` foundation, we'll deliver:

1. **Proactive Quota Management** - Prevent quota failures before they occur
2. **Automated Cost Optimization** - Identify and eliminate waste (30% savings target)
3. **Performance Tuning** - Optimize NFS for multi-VM scenarios (20% improvement)
4. **Safety First** - Multiple safety mechanisms prevent data loss
5. **User-Friendly** - Clear CLI commands and comprehensive documentation

Each module is self-contained, testable, and follows azlin's zero-BS implementation philosophy. The phased approach allows fer incremental delivery of value, startin' with the highest-impact features (quota management and orphaned cleanup) in the first two weeks.

**Next Steps**:
1. Review and approve this specification
2. Create detailed module specifications in separate files
3. Begin Phase 1 implementation (Storage Quota Manager)
4. Iterate based on user feedback and actual cost/performance data

Yarrr! This be a treasure map to storage management excellence! 🏴‍☠️
