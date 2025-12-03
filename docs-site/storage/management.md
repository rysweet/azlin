# Storage Management

Advanced storage management with quota monitoring, automated cleanup, and intelligent tier optimization.

## Overview

azlin v0.4.0 introduces comprehensive storage management features to optimize costs and maintain storage health.

**Key Features:**

- **Quota Management**: Monitor and manage Azure storage quotas
- **Automated Cleanup**: Automatically remove old/unused data
- **Tier Optimization**: Move data to appropriate storage tiers
- **Storage Analytics**: Understand storage usage patterns
- **Cost Optimization**: Reduce storage costs automatically
- **Capacity Planning**: Forecast storage needs

## Quick Start

### Monitor Storage Quotas

```bash
# Check current quota usage
azlin storage quota

# Output:
# Storage Quota Usage:
#   Used: 850 GB / 1000 GB (85%)
#   File Count: 1.2M / 5M (24%)
#   Warning: Approaching quota limit
```

### Enable Auto-Cleanup

```bash
# Enable automated cleanup
azlin storage cleanup enable \
  --remove-temp-older-than 7d \
  --remove-logs-older-than 30d \
  --remove-backups-older-than 90d

# Run cleanup now
azlin storage cleanup run --dry-run
```

### Optimize Storage Tiers

```bash
# Analyze tier optimization opportunities
azlin storage optimize --analyze

# Apply recommendations
azlin storage optimize --apply \
  --move-cold-data-to-cool \
  --age-threshold 30d
```

## Quota Management

### Monitor Quotas

```bash
# Detailed quota breakdown
azlin storage quota --detailed

# Set quota alerts
azlin storage quota alert \
  --threshold 90 \
  --notify admin@example.com

# Request quota increase
azlin storage quota request-increase \
  --new-limit 2000GB \
  --justification "Growing dataset"
```

## Automated Cleanup

### Cleanup Policies

```bash
# Configure cleanup policies
azlin storage cleanup policy create \
  --name "temp-files" \
  --path "/tmp" \
  --older-than 7d \
  --schedule daily

azlin storage cleanup policy create \
  --name "old-logs" \
  --path "/var/log" \
  --older-than 30d \
  --compress-before-delete \
  --schedule weekly
```

### Safe Cleanup

```bash
# Preview what will be deleted
azlin storage cleanup preview --all-policies

# Run with safety checks
azlin storage cleanup run --safe-mode

# Cleanup with exclusions
azlin storage cleanup run \
  --exclude "*.important" \
  --exclude "/data/permanent/*"
```

## Tier Optimization

### Storage Tier Analysis

```bash
# Analyze data access patterns
azlin storage analyze-access

# Recommend tier changes
azlin storage tier recommend

# Output:
# Tier Optimization Recommendations:
#   Move to Cool tier: 250 GB (save $12/month)
#   Move to Archive: 500 GB (save $35/month)
#   Total potential savings: $47/month
```

### Apply Tier Changes

```bash
# Move cold data to Cool tier
azlin storage tier optimize \
  --no-access-days 30 \
  --target-tier cool

# Archive old data
azlin storage tier optimize \
  --no-access-days 90 \
  --target-tier archive
```

## Storage Analytics

```bash
# View storage breakdown
azlin storage analyze

# Find largest files/directories
azlin storage analyze --largest 20

# Identify duplicate files
azlin storage analyze --find-duplicates

# Show storage trends
azlin storage analyze --trends --last 90d
```

## Cost Optimization

```bash
# Storage cost analysis
azlin storage cost

# Show savings opportunities
azlin storage cost --recommendations

# Apply cost optimizations
azlin storage cost optimize \
  --compression \
  --deduplication \
  --tiering
```

## Best Practices

1. **Monitor Quotas Proactively**
   - Set alerts at 80% usage
   - Plan for growth
   - Request increases early

2. **Implement Regular Cleanup**
   - Automate temp file removal
   - Compress old logs
   - Archive infrequently accessed data

3. **Use Appropriate Storage Tiers**
   - Hot tier: Frequently accessed data
   - Cool tier: Infrequently accessed (< 1/month)
   - Archive tier: Rarely accessed (< 1/year)

4. **Enable Compression**
   - Compress logs and backups
   - Use native Azure compression
   - Balance compression vs. access speed

## See Also

- [Storage Overview](./index.md)
- [Azure Files NFS](./mounting.md)
- [Cost Optimization](../monitoring/cost-optimization.md)
- [Storage Commands](../commands/storage/index.md)

---

*Documentation last updated: 2025-12-03*

!!! note "Full Documentation Coming Soon"
    Complete configuration guides, API reference, and advanced examples will be added in the next documentation update.
