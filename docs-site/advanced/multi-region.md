# Multi-Region Orchestration

Deploy, manage, and failover Azure VMs across multiple regions with automated synchronization and intelligent load balancing.

## Overview

azlin v0.4.0 introduces comprehensive multi-region orchestration capabilities that enable high-availability architectures, disaster recovery, and geographic load distribution.

**Key Features:**

- **Parallel Deployment**: Deploy VMs across multiple regions simultaneously
- **Cross-Region Sync**: Automatically synchronize data between regions
- **Intelligent Failover**: Automatic region failover on outages
- **Load Balancing**: Distribute workloads across regions
- **Region Health Monitoring**: Continuous monitoring of region availability
- **Cost Optimization**: Deploy to lowest-cost regions automatically

## Quick Start

### Deploy to Multiple Regions

```bash
# Deploy VM to multiple regions
azlin new myapp \
  --regions eastus,westus,centralus \
  --replicas 1

# Deploy with automatic region selection
azlin new myapp \
  --multi-region auto \
  --count 3

# Deploy with region preferences
azlin new myapp \
  --regions eastus,westus \
  --primary eastus
```

**Output**:
```
🌍 Multi-Region Deployment Started

Regions: eastus (primary), westus, centralus
VMs per Region: 1
Total VMs: 3

Deploying in parallel...
  ✓ eastus:    myapp-eastus-01 (3.2 minutes)
  ✓ westus:    myapp-westus-01 (3.5 minutes)
  ✓ centralus: myapp-centralus-01 (3.8 minutes

)

✓ Cross-region sync configured
✓ Health monitoring enabled
✓ Failover rules applied

Primary Endpoint: myapp-eastus-01.eastus.cloudapp.azure.com
Failover Endpoint: myapp-westus-01.westus.cloudapp.azure.com
```

### Enable Cross-Region Sync

```bash
# Enable data synchronization
azlin region sync enable myapp \
  --data-path /mnt/shared \
  --sync-interval 5m

# Configure sync strategy
azlin region sync configure myapp \
  --strategy active-active \
  --conflict-resolution latest-wins
```

### Configure Failover

```bash
# Enable automatic failover
azlin region failover enable myapp \
  --health-check-interval 30s \
  --failover-threshold 3

# Test failover
azlin region failover test myapp --from eastus --to westus
```

## Multi-Region Deployment

### Deployment Strategies

#### 1. Active-Active (Load Balanced)

Deploy identical VMs across regions for high availability:

```bash
azlin new webapp \
  --regions eastus,westus,centralus \
  --strategy active-active \
  --load-balancer enable

# All regions serve traffic simultaneously
# Traffic is distributed based on geographic proximity
```

**Benefits:**
- Zero downtime
- Lowest latency for users
- Automatic load distribution

**Use Cases:**
- Web applications
- API services
- Content delivery

#### 2. Active-Passive (Failover Only)

Deploy primary VMs with standby replicas:

```bash
azlin new database \
  --regions eastus,westus \
  --strategy active-passive \
  --primary eastus

# Primary region handles all traffic
# Secondary region remains on standby
# Failover activates secondary on primary failure
```

**Benefits:**
- Lower costs (secondary can be smaller)
- Simple failover logic
- Data consistency easier

**Use Cases:**
- Databases
- Stateful applications
- Single-master systems

#### 3. Active-Regional (Geographic Distribution)

Deploy region-specific VMs for local users:

```bash
azlin new app \
  --regions eastus,westeu,eastasia \
  --strategy active-regional \
  --routing geographic

# Each region serves local users
# No cross-region traffic
# Independent scaling per region
```

**Benefits:**
- Compliance with data residency
- Optimal latency per region
- Independent regional operations

**Use Cases:**
- GDPR-compliant applications
- Region-specific services
- Local content delivery

### Parallel Deployment

Deploy to multiple regions simultaneously:

```bash
# Deploy 3 VMs in parallel across regions
azlin new myapp --multi-region auto --count 3 --parallel

# Monitor deployment progress
azlin region deployment status myapp

# Deployment output with progress
Deploying myapp across 3 regions (parallel)...

[eastus]    ████████████████████ 100% (3.2 min)
[westus]    ████████████████████ 100% (3.5 min)
[centralus] ████████████████████ 100% (3.8 min)

Total Time: 3.8 minutes (vs. 10.5 minutes sequential)
Speedup: 2.8x
```

## Cross-Region Synchronization

### Sync Strategies

#### Active-Active Sync (Bi-Directional)

```bash
azlin region sync enable myapp \
  --strategy active-active \
  --sync-interval 5m \
  --conflict-resolution latest-wins
```

**How it works:**
- All regions can write data
- Changes sync bidirectionally
- Conflicts resolved automatically

**Conflict Resolution Options:**
- `latest-wins`: Most recent change wins
- `primary-wins`: Primary region always wins
- `manual`: Flag conflicts for review

#### Active-Passive Sync (One-Way)

```bash
azlin region sync enable myapp \
  --strategy active-passive \
  --source eastus \
  --targets westus,centralus \
  --sync-mode async
```

**How it works:**
- Primary region is source of truth
- Changes replicate one-way to secondaries
- No write conflicts

### Sync Configuration

```bash
# Configure sync details
azlin region sync configure myapp \
  --data-path /mnt/shared \
  --sync-interval 5m \
  --bandwidth-limit 100MB \
  --compression enable

# Monitor sync status
azlin region sync status myapp

# Sync status output
Cross-Region Sync Status: myapp

Strategy: active-active
Sync Interval: 5 minutes
Last Sync: 2 minutes ago

Regions:
  eastus    ✓ In sync (2m ago)
  westus    ✓ In sync (2m ago)
  centralus ⚠ Lag detected (8m ago)

Data Transfer (last hour):
  eastus → westus: 125 MB
  westus → eastus: 98 MB
  eastus → centralus: 105 MB (slow connection)

Conflicts Resolved: 3 (latest-wins)
```

## Failover Management

### Automatic Failover

Configure automatic failover on region failures:

```bash
# Enable automatic failover
azlin region failover enable myapp \
  --health-check-interval 30s \
  --failure-threshold 3 \
  --auto-failback enable

# Configure failover priority
azlin region failover set-priority myapp \
  --primary eastus \
  --secondary westus \
  --tertiary centralus
```

**Failover Triggers:**
- Region health check failures
- Network connectivity issues
- VM unavailability
- Manual failover command

### Manual Failover

Manually trigger failover for maintenance or testing:

```bash
# Initiate manual failover
azlin region failover start myapp --from eastus --to westus

# Failover output
Initiating Failover: myapp
From: eastus → To: westus

Steps:
  1. ✓ Verified westus health (healthy)
  2. ✓ Synced latest data to westus (30 seconds)
  3. ✓ Updated DNS/load balancer to westus
  4. ✓ Verified traffic routing to westus
  5. ✓ Gracefully stopped eastus (draining connections)

Failover Complete (2.5 minutes)
New Primary: westus
Previous Primary: eastus (stopped)

Traffic is now served from westus
```

### Failover Testing

Test failover without affecting production:

```bash
# Dry-run failover test
azlin region failover test myapp \
  --from eastus \
  --to westus \
  --dry-run

# Actual failover test with automated rollback
azlin region failover test myapp \
  --from eastus \
  --to westus \
  --duration 10m \
  --auto-rollback
```

### Failback

Return to original region after failover:

```bash
# Automatic failback (when enabled)
# Triggers when primary region becomes healthy

# Manual failback
azlin region failback myapp --to eastus

# Failback with sync verification
azlin region failback myapp \
  --to eastus \
  --verify-sync \
  --wait-for-health
```

## Region Health Monitoring

### Health Checks

```bash
# View region health
azlin region health

# Detailed health for specific app
azlin region health myapp --detailed

# Region health output
Region Health Status

eastus (Primary)
  Status: ✓ Healthy
  VMs: 3/3 running
  Latency: 12ms (avg)
  Last Check: 15 seconds ago

westus (Secondary)
  Status: ✓ Healthy
  VMs: 3/3 running
  Latency: 45ms (avg)
  Last Check: 18 seconds ago

centralus (Tertiary)
  Status: ⚠ Degraded
  VMs: 2/3 running (1 stopped)
  Latency: 125ms (high)
  Last Check: 20 seconds ago
  Issue: Network latency spike detected
```

### Monitoring Configuration

```bash
# Configure health monitoring
azlin region health configure myapp \
  --interval 30s \
  --latency-threshold 100ms \
  --availability-threshold 95

# Set up alerts
azlin region health alerts myapp \
  --email admin@example.com \
  --slack https://hooks.slack.com/... \
  --trigger "region-degraded" \
  --trigger "failover-initiated"
```

## Cost Optimization

### Deploy to Lowest-Cost Regions

```bash
# Analyze region costs
azlin region costs --for Standard_D4s_v3

# Region cost comparison
Region Cost Analysis: Standard_D4s_v3

eastus:      $140.16/month (baseline)
westus:      $140.16/month (same)
centralus:   $126.14/month (10% cheaper) ⭐
eastus2:     $140.16/month (same)
westeurope:  $156.82/month (12% more expensive)

Recommendation: Deploy to centralus for cost savings
```

```bash
# Deploy to lowest-cost regions
azlin new myapp \
  --multi-region auto \
  --count 3 \
  --optimize cost

# Output
Selected Regions (optimized for cost):
  1. centralus   ($126/month per VM)
  2. southcentralus ($126/month per VM)
  3. eastus      ($140/month per VM)

Estimated Monthly Cost: $392
vs. eastus-only deployment: $420 (7% savings)
```

## Advanced Features

### Geographic Load Balancing

```bash
# Enable geographic load balancing
azlin region loadbalancer enable myapp \
  --routing-method geographic \
  --health-probe /health

# Configure routing rules
azlin region loadbalancer configure myapp \
  --na-region eastus \
  --eu-region westeurope \
  --asia-region eastasia

# Monitor load distribution
azlin region loadbalancer stats myapp
```

### Region-Specific Configuration

Apply different configurations per region:

```bash
# Set region-specific VM sizes
azlin region config myapp \
  --region eastus --vm-size Standard_D4s_v3 \
  --region westus --vm-size Standard_D2s_v3

# Set region-specific environment variables
azlin region env myapp \
  --region eastus --set REGION=us-east \
  --region westeurope --set REGION=eu-west
```

### Cross-Region VNet Peering

```bash
# Enable VNet peering between regions
azlin region network peer \
  --regions eastus,westus \
  --allow-forwarding

# Configure private connectivity
azlin region network configure \
  --private-link enable \
  --bandwidth 1Gbps
```

## Best Practices

1. **Start with Two Regions**
   - Primary and one failover region
   - Add more as needed
   - Keep regions geographically diverse

2. **Test Failover Regularly**
   - Monthly failover tests minimum
   - Document failover procedures
   - Verify data sync after each test

3. **Monitor Cross-Region Latency**
   - Set up latency alerts
   - Use regions with good connectivity
   - Consider ExpressRoute for critical apps

4. **Plan for Data Residency**
   - Check compliance requirements
   - Keep data in required regions
   - Use region-specific storage

5. **Optimize Costs**
   - Use lower-cost regions where possible
   - Right-size secondary region VMs
   - Consider active-passive for cost savings

6. **Implement Health Checks**
   - Comprehensive health monitoring
   - Multiple check types
   - Appropriate thresholds

## API Reference

```python
from azlin.modules.parallel_deployer import MultiRegionDeployer
from azlin.modules.cross_region_sync import CrossRegionSync
from azlin.modules.region_failover import FailoverManager

# Deploy to multiple regions
deployer = MultiRegionDeployer()
deployment = deployer.deploy(
    app_name="myapp",
    regions=["eastus", "westus", "centralus"],
    strategy="active-active",
    parallel=True
)

# Enable cross-region sync
sync = CrossRegionSync(app_name="myapp")
sync.enable(
    strategy="active-active",
    sync_interval=300,  # 5 minutes
    conflict_resolution="latest-wins"
)

# Configure failover
failover = FailoverManager(app_name="myapp")
failover.enable_automatic(
    health_check_interval=30,
    failure_threshold=3,
    auto_failback=True
)

# Monitor region health
health = failover.get_region_health()
for region, status in health.items():
    print(f"{region}: {status.status} ({status.latency}ms)")
```

## Troubleshooting

### Sync Lag Issues

**Problem**: Cross-region sync falling behind

**Solution**:
```bash
# Check sync status
azlin region sync status myapp --verbose

# Increase bandwidth
azlin region sync configure myapp --bandwidth-limit 500MB

# Reduce sync interval for critical data
azlin region sync configure myapp --sync-interval 2m
```

### Failover Not Triggering

**Problem**: Automatic failover not activating

**Solution**:
```bash
# Verify failover configuration
azlin region failover show myapp

# Check health monitoring
azlin region health myapp --logs

# Test health checks manually
azlin region health check myapp --region eastus
```

## See Also

- [VM Lifecycle Automation](../vm-lifecycle/automation.md)
- [Backup & Disaster Recovery](./backup-dr.md)
- [High Availability Guide](./high-availability.md)
- [Cost Optimization](../monitoring/cost-optimization.md)

---

*Documentation last updated: 2025-12-03*
