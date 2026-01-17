# Cost Optimization Intelligence

**Version**: 0.4.0
**Status**: Production
**Last Updated**: 2025-12-01

azlin provides comprehensive cost optimization intelligence to help you minimize Azure spending while maintaining performance.

## Overview

The cost optimization system provides:

1. **Real-Time Cost Dashboard** - Monitor current spending across all VMs
2. **Budget Alerts & Forecasting** - Get notified before exceeding budgets
3. **Optimization Recommendations** - AI-powered suggestions to reduce costs
4. **Cost History & Trends** - Track spending patterns over time
5. **Automated Optimization** - Schedule actions to reduce costs automatically

## Quick Start

```bash
# View real-time cost dashboard
azlin costs show

# Set budget and enable alerts
azlin costs budget set 500

# Get optimization recommendations
azlin costs recommendations

# View cost forecast
azlin costs forecast

# Enable automated cost optimization
azlin costs optimize --enable
```

## Commands

### Real-Time Cost Dashboard

View current spending across all VMs with real-time updates from Azure Cost Management API.

```bash
# Show dashboard for current resource group
azlin costs show

# Show dashboard for specific resource group
azlin costs show --rg my-resource-group

# Show per-VM breakdown
azlin costs show --by-vm

# Refresh dashboard (bypass cache)
azlin costs show --refresh
```

**Output Example**:
```
================================================================================
Azure Cost Dashboard (Real-Time)
================================================================================
Resource Group: azlin-rg-1234567890
Last Updated: 2025-12-01 14:30:00 UTC
Billing Period: Dec 1 - Dec 31, 2025

Total Spending (This Month):  $247.50
Daily Average:                $23.45
Projected Month-End Total:    $726.39

Running VMs: 3
Stopped VMs: 1

================================================================================
Per-VM Breakdown
================================================================================
VM NAME                   STATUS    DAILY COST   MONTH-TO-DATE   PROJECTED
azlin-vm-001             Running   $9.60        $105.60         $297.60
azlin-vm-002             Running   $8.32        $91.52          $257.92
azlin-vm-003             Running   $5.53        $60.83          $171.33
azlin-vm-004             Stopped   $0.00        $0.00           $0.00

================================================================================
```

**Performance**: Response time < 2 seconds (includes 5-minute cache)

### Budget Management

Set budgets and receive alerts when spending reaches thresholds.

```bash
# Set monthly budget
azlin costs budget set 500

# Set budget with custom thresholds
azlin costs budget set 500 --thresholds 75,85,95

# Check budget status
azlin costs budget status

# Disable budget alerts
azlin costs budget disable
```

**Budget Alert Thresholds**:
- **80% threshold**: Warning notification
- **90% threshold**: Critical notification
- **100% threshold**: Alert + optional auto-shutdown of non-essential VMs

**Output Example**:
```
================================================================================
Budget Status
================================================================================
Monthly Budget:           $500.00
Current Spending:         $247.50 (49.5%)
Remaining Budget:         $252.50
Projected Month-End:      $726.39

⚠️  WARNING: Projected spending ($726.39) will exceed budget by $226.39 (45%)

Alert Thresholds:
  ✓ 80% ($400.00) - Not reached
  ✓ 90% ($450.00) - Not reached
  ✓ 100% ($500.00) - Not reached

Recommendation: Consider optimization actions to stay within budget
================================================================================
```

### Cost Forecasting

Predict end-of-month costs based on current usage patterns and historical data.

```bash
# Show forecast for current month
azlin costs forecast

# Show forecast with confidence intervals
azlin costs forecast --confidence

# Forecast specific resource group
azlin costs forecast --rg my-resource-group
```

**Forecast Accuracy**: Within 10% of actual costs (based on 30-day rolling average)

**Output Example**:
```
================================================================================
Cost Forecast
================================================================================
Current Month: December 2025
Days Elapsed: 10 / 31 (32%)
Days Remaining: 21

Current Spending:         $247.50
Daily Average:            $24.75

End-of-Month Projection:  $767.25
Confidence Interval:      $690.53 - $843.98 (90% confidence)
Forecast Accuracy:        92% (based on historical data)

Trend Analysis:
  - Spending increased 15% compared to last month
  - Highest cost VM: azlin-vm-001 ($297.60 projected)
  - Potential savings with optimization: $150 - $200/month

================================================================================
```

### Optimization Recommendations

Get AI-powered recommendations to reduce costs without sacrificing performance.

```bash
# Show all recommendations
azlin costs recommendations

# Filter by savings potential
azlin costs recommendations --min-savings 50

# Show only high-confidence recommendations
azlin costs recommendations --confidence high

# Export recommendations to file
azlin costs recommendations --export recommendations.json
```

**Recommendation Types**:
1. **Downsize VMs** - Identify over-provisioned VMs
2. **Schedule Start/Stop** - Automate VM shutdown during off-hours
3. **Cheaper VM Sizes** - Suggest cost-effective alternatives
4. **Region Migration** - Recommend lower-cost regions
5. **Reserved Instances** - Identify VMs suitable for reservations

**Output Example**:
```
================================================================================
Cost Optimization Recommendations
================================================================================
Total Potential Savings: $180.25/month (24% reduction)

[1] Downsize VM: azlin-vm-001
    Current: Standard_D8s_v3 ($297.60/month)
    Recommended: Standard_D4s_v3 ($148.80/month)
    Savings: $148.80/month (50% reduction)
    Confidence: High (85%)
    Reason: Average CPU utilization <15% for past 30 days
    Action: azlin costs optimize downsize azlin-vm-001 --size Standard_D4s_v3

[2] Schedule Stop/Start: azlin-vm-002
    Current: Running 24/7 ($257.92/month)
    Recommended: Stop 8PM-8AM weekdays
    Savings: $77.38/month (30% reduction)
    Confidence: Medium (70%)
    Reason: No activity detected outside business hours
    Action: azlin costs optimize schedule azlin-vm-002 --hours "8-20" --days "Mon-Fri"

[3] Switch to AMD: azlin-vm-003
    Current: Standard_D2s_v5 Intel ($171.33/month)
    Recommended: Standard_D2as_v5 AMD ($154.20/month)
    Savings: $17.13/month (10% reduction)
    Confidence: High (90%)
    Reason: AMD equivalent performs identically at lower cost
    Action: azlin costs optimize migrate azlin-vm-003 --size Standard_D2as_v5

================================================================================
```

### Cost History & Trends

Analyze spending patterns over 30, 60, or 90 days.

```bash
# Show 30-day cost history
azlin costs history

# Show 90-day trend
azlin costs history --days 90

# Compare periods
azlin costs history --compare

# Export to CSV
azlin costs history --export history.csv
```

**Output Example**:
```
================================================================================
Cost History (Last 30 Days)
================================================================================

Daily Spending Trend:
Dec 1:  $23.45  ████████████████
Dec 2:  $24.10  ████████████████▌
Dec 3:  $22.80  ███████████████
Dec 4:  $25.50  ████████████████████
...

Weekly Averages:
Week 1 (Dec 1-7):   $23.12/day  ($161.84 total)
Week 2 (Dec 8-14):  $25.45/day  ($178.15 total)

Monthly Comparison:
November 2025:  $687.50
December 2025:  $726.39 (projected) [+5.7%]
October 2025:   $642.10

Cost by VM (30-day total):
azlin-vm-001:  $288.00 (40%)
azlin-vm-002:  $249.60 (35%)
azlin-vm-003:  $166.40 (23%)
azlin-vm-004:  $15.00 (2%)

================================================================================
```

### Automated Optimization

Enable automated cost optimization actions with approval workflows.

```bash
# Enable automated optimization
azlin costs optimize --enable

# Configure optimization rules
azlin costs optimize config

# Show optimization status
azlin costs optimize status

# Manually trigger optimization
azlin costs optimize run

# Disable automated optimization
azlin costs optimize --disable
```

**Optimization Actions**:
1. **Auto-Shutdown** - Stop VMs exceeding idle thresholds
2. **Scheduled Start/Stop** - Automate VM schedules
3. **Auto-Downsize** - Resize underutilized VMs (requires approval)
4. **Budget Protection** - Stop non-essential VMs when budget limit reached

**Approval Workflow**:
- **No approval**: Schedule stop/start
- **Auto-approval**: Auto-shutdown after 24h idle
- **Manual approval**: VM downsizing, region migration

**Output Example**:
```
================================================================================
Automated Optimization Status
================================================================================
Status: Enabled
Last Run: 2025-12-01 08:00:00 UTC
Next Run: 2025-12-02 08:00:00 UTC (daily at 8 AM)

Active Rules:
[✓] Auto-shutdown idle VMs after 24 hours
[✓] Enforce business-hours schedule for dev VMs (tag: env=dev)
[✓] Budget protection at 95% threshold
[✗] Auto-downsize (requires manual approval)

Recent Actions (Last 7 Days):
- 2025-11-30: Stopped azlin-vm-004 (idle 48 hours) - Saved $2.30
- 2025-11-29: Applied schedule to azlin-vm-002 - Projected $77/month savings
- 2025-11-28: Budget alert sent (85% threshold)

Total Savings (This Month): $45.60

================================================================================
```

## Configuration

Cost optimization settings stored in `~/.azlin/config.toml`:

```toml
[costs]
# Cache API responses for 5 minutes
cache_ttl = 300

# Budget settings
monthly_budget = 500.00
budget_alerts = [80, 90, 100]

# Optimization settings
auto_optimization = true
require_approval_for_downsize = true
idle_threshold_hours = 24

# Data storage
storage_backend = "json"  # "json" or "sqlite"
history_retention_days = 90
```

## Data Storage

Cost data stored in `~/.azlin/costs/`:

```
~/.azlin/costs/
├── history.json          # Cost history (30/60/90 days)
├── budgets.json          # Budget configurations
├── cache.json            # API response cache
└── recommendations.json  # Optimization recommendations
```

## API Integration

Uses Azure Cost Management API for real-time cost data:

- **Authentication**: Azure SDK credentials (same as azlin)
- **API**: `azure-mgmt-costmanagement`
- **Caching**: 5-minute TTL to meet <2s response time
- **Fallback**: Uses estimation if API unavailable

## Performance

- **Dashboard load time**: < 2 seconds (with caching)
- **Forecast accuracy**: Within 10% of actual costs
- **Cache TTL**: 5 minutes
- **Data retention**: 90 days

## Best Practices

1. **Set budgets early** - Enable alerts before costs spiral
2. **Review recommendations weekly** - Act on high-confidence suggestions
3. **Use tags** - Tag VMs by environment for better tracking
4. **Schedule dev VMs** - Stop development VMs outside business hours
5. **Monitor forecasts** - Track trends to avoid budget surprises

## Troubleshooting

### Cost data not updating

```bash
# Refresh cache
azlin costs show --refresh

# Check Azure credentials
azlin auth test
```

### Budget alerts not working

```bash
# Verify budget configuration
azlin costs budget status

# Check notification settings
cat ~/.azlin/config.toml | grep budget
```

### Recommendations seem inaccurate

Recommendations based on 30-day rolling average. For newly created VMs, wait 7-14 days for accurate utilization data.

## Related Documentation

- [Cost Tracking Overview](cost-tracking.md)
- [Budget Management Guide](budget-management.md)
- [Optimization Strategies](optimization-strategies.md)
- [Azure Cost Management API](https://docs.microsoft.com/azure/cost-management-billing/)

---

**Note**: Cost data updates every 24 hours in Azure. Real-time dashboard reflects latest available data with 5-minute caching.
