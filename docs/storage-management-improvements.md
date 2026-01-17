# Storage Management Improvements

**Author**: azlin team
**Last Updated**: 2025-12-01
**Version**: 1.0

## Overview

Ahoy! This guide covers azlin's enhanced storage management capabilities fer quota management, cost optimization, performance tuning, and automated cleanup. These features help ye manage Azure storage resources efficiently, reduce costs by up to 30%, and improve NFS performance by 20%.

## Quick Start

```bash
# Check yer storage costs
azlin storage cost analyze

# Find orphaned resources wastin' doubloons
azlin storage cleanup scan

# Set a quota to prevent overspending
azlin storage quota set --scope team --name my-team-rg --quota 2000

# Optimize NFS performance fer multi-VM workloads
azlin storage nfs tune my-shared-storage --vm my-dev-vm
```

## Storage Quota Management

### Overview

Storage quotas help ye prevent unexpected costs by settin' limits at the VM, team (resource group), or project (subscription) level. azlin tracks usage across storage accounts, managed disks, and snapshots, enforcin' quotas before operations that would exceed limits.

### Setting Quotas

**VM-level quota** (limit storage fer a single VM):

```bash
azlin storage quota set --scope vm --name my-dev-vm --quota 500
```

This sets a 500 GB quota fer all storage resources associated with `my-dev-vm`, includin':
- Mounted storage accounts
- VM OS and data disks
- VM snapshots

**Team-level quota** (limit storage fer a resource group):

```bash
azlin storage quota set --scope team --name azlin-dev-rg --quota 2000
```

This sets a 2 TB quota fer all storage resources in the `azlin-dev-rg` resource group.

**Project-level quota** (limit storage fer entire subscription):

```bash
azlin storage quota set --scope project --quota 10000
```

This sets a 10 TB quota fer all storage resources in yer current subscription.

### Checking Quota Status

View current usage and available capacity:

```bash
azlin storage quota status --scope vm --name my-dev-vm
```

**Example output**:

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

### Listing All Quotas

View all configured quotas:

```bash
azlin storage quota list
azlin storage quota list --scope team
```

### Quota Enforcement

Quotas are automatically checked before:
- Creating storage accounts (`azlin storage create`)
- Creating VMs (`azlin new`)
- Creating snapshots

If an operation would exceed the quota, ye'll see a clear error message:

```
❌ Quota exceeded: my-dev-vm
Current usage: 487 GB
Quota: 500 GB
Requested: 50 GB
Remaining: 13 GB

Cannot create storage account (50 GB) - would exceed quota by 37 GB.

To proceed:
  1. Clean up unused resources: azlin storage cleanup scan
  2. Increase quota: azlin storage quota set --scope vm --name my-dev-vm --quota 550
```

### Removing Quotas

```bash
azlin storage quota remove --scope vm --name my-dev-vm
```

## Cost Optimization

### Cost Analysis

Get a comprehensive breakdown of yer storage costs:

```bash
azlin storage cost analyze
azlin storage cost analyze --resource-group azlin-rg
```

**Example output**:

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

### Cost Recommendations

Get detailed optimization recommendations:

```bash
azlin storage cost recommendations
azlin storage cost recommendations --sort-by savings
azlin storage cost recommendations --min-savings 10
```

Each recommendation includes:
- Category (tier optimization, orphaned cleanup, snapshot retention, resize)
- Resource details
- Current vs potential costs
- Effort and risk assessment
- Priority ranking

### Estimating Savings

Get total savings potential:

```bash
azlin storage cost savings
```

### Cost Reports

Generate reports in multiple formats:

```bash
# Human-readable text (default)
azlin storage cost report

# Machine-readable JSON
azlin storage cost report --format json

# CSV fer spreadsheet analysis
azlin storage cost report --format csv --output costs.csv
```

## Storage Tier Optimization

### Overview

Azure offers Premium and Standard storage tiers with different cost and performance characteristics:

- **Premium**: $0.1536/GB/month - High performance (4 GB/s reads, 2 GB/s writes)
- **Standard**: $0.04/GB/month - Standard performance (60 MB/s)

Many workloads over-provision by usin' Premium when Standard would suffice, wastin' 74% of storage costs.

### Analyzing Storage Tiers

Analyze usage patterns fer a specific storage account:

```bash
azlin storage tier analyze myteam-shared
```

**Example output**:

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

### Getting Recommendations

Get tier recommendations fer specific storage:

```bash
azlin storage tier recommend myteam-shared
```

### Auditing All Storage

Audit all storage accounts in yer resource group:

```bash
azlin storage tier audit
azlin storage tier audit --resource-group azlin-rg
```

### Migrating Tiers

**IMPORTANT**: Azure doesn't support in-place tier changes. Migration creates a new storage account, copies data, updates VM mounts, and deletes the old storage after verification.

**Dry run** (shows what would happen):

```bash
azlin storage tier migrate myteam-shared --tier Standard
```

**Actually migrate** (requires confirmation):

```bash
azlin storage tier migrate myteam-shared --tier Standard --confirm
```

The migration process:

1. Creates new storage account with target tier
2. Copies all data using Azure storage copy
3. Updates VM mount configurations
4. Verifies data integrity
5. Deletes old storage after confirmation

**Downtime**: VMs will need temporary dual-mount or brief unmount during migration. Plan accordingly.

### Rollback

If migration fails or performance isn't acceptable, ye can migrate back:

```bash
azlin storage tier migrate myteam-shared-new --tier Premium --confirm
```

The old storage is kept until ye confirm deletion, allowin' safe rollback.

## Orphaned Resource Cleanup

### Overview

Orphaned resources are storage assets no longer attached to VMs, includin':

- **Orphaned disks**: Managed disks not attached to any VM
- **Orphaned snapshots**: Snapshots of deleted VMs
- **Orphaned storage**: Storage accounts with no connected VMs

These resources continue costin' money even when unused. Typical savings: $100-$200/month fer a small team.

### Scanning fer Orphaned Resources

**Scan all resource types**:

```bash
azlin storage cleanup scan
azlin storage cleanup scan --resource-group azlin-rg
```

**Scan specific resource type**:

```bash
azlin storage cleanup scan --type disk
azlin storage cleanup scan --type snapshot
azlin storage cleanup scan --type storage
```

**Adjust minimum age** (default: 7 days fer disks, 30 days fer snapshots/storage):

```bash
azlin storage cleanup scan --min-age-days 30
```

**Example output**:

```
Orphaned Resources Scan: azlin-dev-rg
=====================================
Scan Date: 2025-12-01 15:30:00

Orphaned Managed Disks (3):
  1. old-vm-OsDisk_1
     Size: 128 GB | Age: 45 days | Cost: $9.83/mo
     Reason: VM deleted, disk unattached fer 45 days

  2. test-datadisk_0
     Size: 256 GB | Age: 12 days | Cost: $19.66/mo
     Reason: No longer attached to any VM

  3. backup-disk-old
     Size: 512 GB | Age: 90 days | Cost: $20.48/mo
     Reason: Standard disk unattached fer 90 days

Orphaned Snapshots (5):
  1. deleted-vm-snapshot-20251101
     Size: 128 GB | Age: 30 days | Cost: $6.40/mo
     Reason: Source VM no longer exists

  [... 4 more snapshots ...]

Orphaned Storage Accounts (1):
  1. oldprojectstorage
     Size: 100 GB | Age: 60 days | Cost: $15.36/mo
     Reason: No VMs connected fer 60 days

Summary:
  Total Resources: 9
  Total Size:      1,324 GB
  Monthly Cost:    $121.43
  Annual Savings:  $1,457.16 (if cleaned)

To delete these resources:
  azlin storage cleanup --type all --confirm
```

### Cleaning Up Orphaned Resources

**Dry run** (shows what would be deleted, default):

```bash
azlin storage cleanup --type all
azlin storage cleanup --type disk --min-age-days 7
azlin storage cleanup --type snapshot --min-age-days 60
```

**Actually delete** (requires `--confirm`):

```bash
azlin storage cleanup --type all --confirm
azlin storage cleanup --type disk --confirm --min-age-days 14
```

### Safety Mechanisms

Multiple safety checks prevent accidental deletion:

1. **Minimum age**: Resources must be orphaned fer minimum days (default: 7-30 days)
2. **Tags**: Resources with `azlin:keep` tag are never deleted
3. **Dry run default**: Must explicitly use `--confirm` to delete
4. **Verification**: Double-checks resource isn't attached before deletion

### Protecting Resources from Cleanup

Tag resources ye want to keep:

```bash
az disk update --name important-backup-disk \
  --resource-group azlin-rg \
  --set tags.azlin:keep=true

az snapshot update --name critical-snapshot \
  --resource-group azlin-rg \
  --set tags.azlin:keep=true

az storage account update --name keepthisstorage \
  --resource-group azlin-rg \
  --tags azlin:keep=true
```

## NFS Performance Tuning

### Overview

Azure Files NFS performance depends heavily on mount options. Default mount options work but aren't optimized fer specific workloads. Proper tuning can improve performance by 15-25%, especially fer multi-VM scenarios.

### Analyzing NFS Performance

Analyze current NFS configuration and identify bottlenecks:

```bash
azlin storage nfs analyze myteam-shared
azlin storage nfs analyze myteam-shared --vm my-dev-vm
```

**Example output**:

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
    ✓ Enable hard mount fer reliability

  Rationale:
    - Larger buffers improve throughput fer large file operations
    - Short attribute cache prevents stale metadata in multi-VM scenario
    - Hard mount ensures I/O operations complete reliably

To apply tuning:
  azlin storage nfs tune myteam-shared --vm my-dev-vm --profile multi-vm

To test current performance:
  azlin storage nfs test --vm my-dev-vm
```

### Getting Tuning Recommendations

Get recommendations without applyin' changes:

```bash
azlin storage nfs tune myteam-shared --recommend
azlin storage nfs tune myteam-shared --workload read-heavy --recommend
```

### Tuning Profiles

azlin provides pre-configured profiles fer common workloads:

**Multi-VM** (default when >1 VM connected):
```
rsize=1048576,wsize=1048576,hard,actimeo=1
```
- Short attribute cache (1s) prevents stale file metadata
- Best fer shared development environments

**Read-heavy** (development, code reading):
```
rsize=1048576,wsize=1048576,hard,ac,acregmin=3,acregmax=60,acdirmin=30,acdirmax=60
```
- Aggressive attribute caching
- Larger read buffers
- Best fer code repositories, documentation

**Write-heavy** (build, CI, logs):
```
rsize=1048576,wsize=1048576,hard,noac,async
```
- Async writes fer performance
- No attribute caching
- Best fer build environments, log aggregation

**Mixed/balanced** (general purpose):
```
rsize=1048576,wsize=1048576,hard,ac,acregmin=10,acregmax=30
```
- Moderate caching
- Large I/O buffers
- Best fer standard development workflows

### Applying Tuning

**Use recommended profile**:

```bash
azlin storage nfs tune myteam-shared --vm my-dev-vm
```

**Use specific profile**:

```bash
azlin storage nfs tune myteam-shared --vm my-dev-vm --profile read-heavy
azlin storage nfs tune myteam-shared --vm my-dev-vm --profile write-heavy
azlin storage nfs tune myteam-shared --vm my-dev-vm --profile multi-vm
```

**Use custom options**:

```bash
azlin storage nfs tune myteam-shared --vm my-dev-vm \
  --custom-options "vers=4.1,rsize=1048576,wsize=1048576,hard,actimeo=5"
```

The tuning process:

1. Backs up current `/etc/fstab`
2. Tests new mount options
3. Updates `/etc/fstab` if successful
4. Remounts storage with new options
5. Verifies mount succeeded

### Testing Performance

**Quick test** (~30 seconds):

```bash
azlin storage nfs test --vm my-dev-vm
```

Uses `dd` commands to test sequential read/write throughput.

**Full test** (~5 minutes, requires `fio`):

```bash
azlin storage nfs test --vm my-dev-vm --type full
```

Runs comprehensive I/O tests includin' random read/write, mixed workloads, and multi-threaded operations.

**Example output**:

```
NFS Performance Test: my-dev-vm
================================
Storage: myteam-shared (Premium)
Test Type: Quick (30 seconds)

Results:
  Sequential Read:   1,234 MB/s
  Sequential Write:    845 MB/s
  Average Latency:    0.8 ms

Expected Performance (Premium NFS):
  Read:  Up to 4,000 MB/s
  Write: Up to 2,000 MB/s
  Latency: <1 ms

Status: Good (within expected range fer single VM)

To compare before/after tuning:
  azlin storage nfs benchmark --vm my-dev-vm --compare
```

### Comparing Before/After Performance

Test performance, apply tuning, test again, and compare:

```bash
# Test current performance
azlin storage nfs test --vm my-dev-vm

# Apply tuning
azlin storage nfs tune myteam-shared --vm my-dev-vm

# Compare performance
azlin storage nfs benchmark --vm my-dev-vm --compare
```

**Example comparison**:

```
Performance Comparison: my-dev-vm
=================================
Storage: myteam-shared

Metric              Before    After     Change
────────────────────────────────────────────
Sequential Read     1,234 MB/s 1,456 MB/s +18.0%
Sequential Write      845 MB/s   987 MB/s +16.8%
Average Latency       0.8 ms     0.7 ms   -12.5%

Overall Improvement: +17.4%

The tuning was successful! Performance improved by 17.4% on average.
```

### Rollback

If performance degrades or issues occur, rollback to original mount options:

```bash
# azlin keeps backup of /etc/fstab
ssh my-dev-vm "sudo cp /etc/fstab.backup /etc/fstab"
ssh my-dev-vm "sudo mount -a"
```

Or re-apply default options:

```bash
azlin storage mount vm myteam-shared --vm my-dev-vm --reset
```

## Common Workflows

### Weekly Cost Review

```bash
# Check current costs
azlin storage cost analyze

# Scan fer orphaned resources
azlin storage cleanup scan

# Get recommendations
azlin storage cost recommendations

# Clean up orphaned resources
azlin storage cleanup --type all --confirm
```

Expected time: 10-15 minutes
Expected savings: $50-$150/month fer typical team

### Quarterly Tier Optimization

```bash
# Audit all storage tiers
azlin storage tier audit

# Review specific storage
azlin storage tier analyze myteam-shared

# Migrate if recommended
azlin storage tier migrate myteam-shared --tier Standard --confirm
```

Expected time: 30-60 minutes (includes migration time)
Expected savings: $10-$50/month per storage account

### New Project Setup

```bash
# Set team quota
azlin storage quota set --scope team --name new-project-rg --quota 1000

# Set individual VM quotas
azlin storage quota set --scope vm --name dev-vm-1 --quota 200
azlin storage quota set --scope vm --name dev-vm-2 --quota 200

# Create shared storage (blob public access disabled by default)
azlin storage create project-shared --size 100 --tier Standard

# Mount and tune fer multi-VM
azlin storage mount vm project-shared --vm dev-vm-1
azlin storage mount vm project-shared --vm dev-vm-2
azlin storage nfs tune project-shared --vm dev-vm-1
azlin storage nfs tune project-shared --vm dev-vm-2
```

Expected time: 20-30 minutes
Expected results: Optimal cost/performance from day one

### Performance Troubleshooting

```bash
# Analyze NFS performance
azlin storage nfs analyze shared-storage

# Test current performance
azlin storage nfs test --vm slow-vm --type full

# Apply tuning
azlin storage nfs tune shared-storage --vm slow-vm

# Compare results
azlin storage nfs benchmark --vm slow-vm --compare
```

Expected time: 15-20 minutes
Expected improvement: 15-25% performance gain

## Best Practices

### Quota Management

1. **Set quotas early**: Configure quotas when creating projects, not after problems occur
2. **Use hierarchical quotas**: Set project quotas first, then team quotas, then VM quotas
3. **Leave headroom**: Set quotas 20% higher than expected usage to avoid false alarms
4. **Monitor regularly**: Check quota status weekly with `azlin storage quota status`

### Cost Optimization

1. **Weekly scans**: Run `azlin storage cleanup scan` weekly to catch orphaned resources early
2. **Review recommendations**: Check `azlin storage cost recommendations` monthly
3. **Start with low-hanging fruit**: Clean up orphaned resources first (highest ROI, lowest risk)
4. **Document decisions**: If ye choose not to implement a recommendation, document why

### Tier Selection

1. **Default to Standard**: Use Standard tier unless ye have proven performance needs
2. **Measure first**: Use `azlin storage nfs test` to verify performance before upgrading to Premium
3. **Multi-VM = Premium**: Consider Premium when >3 VMs share storage
4. **Review quarterly**: Usage patterns change; re-evaluate tier decisions every 3 months

### NFS Tuning

1. **Multi-VM default**: Always use `actimeo=1` when multiple VMs share storage
2. **Test before and after**: Use `azlin storage nfs test` to measure improvement
3. **Workload-specific profiles**: Use read-heavy/write-heavy profiles when workload is clear
4. **Keep backups**: azlin backs up `/etc/fstab` automatically, but verify before tuning

### Safety

1. **Dry run first**: Always run cleanup/migration commands without `--confirm` first
2. **Use tags**: Tag important resources with `azlin:keep=true`
3. **Test in dev**: Test tier migrations and NFS tuning in dev environments first
4. **Monitor performance**: Watch application performance after changes; rollback if issues

### Security

1. **Public access disabled**: All storage accounts created with blob public access disabled by default
2. **Azure policy compliance**: Storage creation automatically complies with "Storage account public access should be disallowed" policy
3. **No configuration needed**: Security enforced automatically without user intervention
4. **VNet-only access**: All storage remains accessible only within Azure VNet (unchanged from previous behavior)

## Troubleshooting

### Quota Exceeded Errors

**Problem**: Operation fails with "quota exceeded" error

**Solution**:
```bash
# Check current usage
azlin storage quota status --scope vm --name my-vm

# Option 1: Clean up unused resources
azlin storage cleanup scan
azlin storage cleanup --type all --confirm

# Option 2: Increase quota
azlin storage quota set --scope vm --name my-vm --quota 600
```

### Orphaned Resources Not Detected

**Problem**: Resources ye know are orphaned don't appear in scan

**Possible causes**:
1. Resources too new (below minimum age threshold)
2. Resources tagged with `azlin:keep`
3. Storage account marked as shared in config

**Solution**:
```bash
# Lower minimum age
azlin storage cleanup scan --min-age-days 1

# Check fer tags
az disk show --name my-disk --resource-group my-rg --query tags

# Remove keep tag if needed
az disk update --name my-disk --resource-group my-rg --remove tags.azlin:keep
```

### Tier Migration Failed

**Problem**: Tier migration fails mid-process

**Solution**:
```bash
# Check migration status
azlin storage list

# If new storage created but old not deleted:
# 1. Verify new storage has all data
azlin storage status new-storage-name

# 2. Manually delete old storage if safe
azlin storage delete old-storage-name --confirm

# If migration failed early:
# Old storage still intact, just retry
azlin storage tier migrate old-storage --tier Standard --confirm
```

### NFS Performance Worse After Tuning

**Problem**: Performance degraded after applyin' NFS tuning

**Solution**:
```bash
# Rollback to original mount options
ssh my-vm "sudo cp /etc/fstab.backup /etc/fstab"
ssh my-vm "sudo mount -a"

# Or reset to defaults
azlin storage mount vm my-storage --vm my-vm --reset

# Try different profile
azlin storage nfs tune my-storage --vm my-vm --profile mixed
```

### Cost Analysis Inaccurate

**Problem**: Cost analysis doesn't match Azure portal

**Explanation**: azlin uses approximate costs ($0.1536/GB Premium, $0.04/GB Standard). Actual costs vary by region and Azure billing details.

**Solution**: Use azlin recommendations as relative comparisons (savings potential), not absolute cost predictions. Cross-reference with Azure Cost Management fer exact costs.

## FAQ

### Q: Will cleanin' up orphaned resources delete my data?

A: Orphaned cleanup only deletes resources that:
1. Are not attached to any VM
2. Meet minimum age requirements (7-30 days)
3. Don't have `azlin:keep` tag
4. Dry-run shows ye exactly what will be deleted before `--confirm`

If ye have backups ye want to keep, tag them: `azlin:keep=true`

### Q: What happens to my data during tier migration?

A: Tier migration creates a new storage account, copies all data, updates VM mounts, and keeps the old storage until ye confirm deletion. Yer data exists in both places until ye verify and complete migration. Budget fer temporary double storage costs during migration.

### Q: Can I tune NFS fer individual VMs differently?

A: Yes! Each VM can have different mount options fer the same storage. Use:
```bash
azlin storage nfs tune my-storage --vm vm-1 --profile read-heavy
azlin storage nfs tune my-storage --vm vm-2 --profile write-heavy
```

This is advanced usage; normally all VMs sharin' storage should use the same `multi-vm` profile.

### Q: Do quotas prevent accidental overspending?

A: Yes, but only fer operations through azlin. Quotas prevent:
- `azlin storage create` from exceeding limits
- `azlin new` from creating VMs that would exceed quota
- Snapshot creation beyond quota

Azure portal operations bypass azlin quotas. Use Azure Cost Management alerts fer comprehensive budget control.

### Q: How often should I run cleanup and optimization?

A: Recommended schedule:
- **Weekly**: `azlin storage cleanup scan` (5 minutes)
- **Monthly**: `azlin storage cost recommendations` (10 minutes)
- **Quarterly**: `azlin storage tier audit` (30 minutes)

Set calendar reminders or automate with cron jobs.

### Q: Is it safe to use async NFS writes?

A: Async writes improve performance but have data consistency risks:
- Safe: Single-VM workloads, non-critical data
- Risky: Multi-VM workloads, databases, critical data

azlin defaults to safer options. Use `async` only fer specific write-heavy workloads where ye can tolerate potential data loss (e.g., build artifacts, logs).

## Related Documentation

- [Storage Management Basics](./storage-basics.md) - Core storage concepts and commands
- [VM Management](./vm-management.md) - VM creation and configuration
- [Snapshot Management](./snapshot-management.md) - Automated backup and retention
- [Cost Optimization Guide](./cost-optimization.md) - Comprehensive cost management strategies

## Support

If ye encounter issues:

1. Check this documentation
2. Run commands with `--help` fer detailed usage
3. Check Azure portal fer resource status
4. Review azlin logs: `~/.azlin/logs/`
5. File an issue: [azlin GitHub Issues](https://github.com/yourusername/azlin/issues)

Yarrr! May yer storage be swift, yer costs be low, and yer data always safe! 🏴‍☠️
