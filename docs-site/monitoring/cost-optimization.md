# Cost Optimization Intelligence

Intelligent cost tracking, budget alerts, and automated optimization recommendations for Azure VM fleets.

## Overview

azlin v0.4.0 introduces comprehensive cost optimization features that help you understand, track, and minimize Azure spending for your VM infrastructure.

**Key Features:**

- **Real-Time Cost Dashboard**: Track spending across VMs, regions, and resource groups
- **Budget Alerts**: Get notified before exceeding budget thresholds
- **Cost Recommendations**: AI-powered suggestions for reducing costs
- **Usage Analytics**: Understand utilization patterns and identify waste
- **Forecasting**: Predict future costs based on historical usage
- **Automated Actions**: Auto-stop idle VMs, deallocate unused resources

## Quick Start

### View Cost Dashboard

```bash
# Show cost summary for all VMs
azlin util cost

# Detailed cost breakdown
azlin util cost --detailed

# Cost by region
azlin util cost --by-region

# Cost for specific time period
azlin util cost --last 30d
```

**Output**:
```
Azure Cost Summary (Last 30 days)
=====================================

Total Spending: $1,247.50
Daily Average: $41.58
Projected Monthly: $1,248.00

By Resource Type:
  Virtual Machines:    $892.00 (71.5%)
  Storage:             $245.00 (19.6%)
  Network:             $88.50  (7.1%)
  Bastion:             $22.00  (1.8%)

Top 5 Cost Contributors:
  1. vm-prod-db-01:    $285.00 (Standard_D8s_v3, eastus)
  2. vm-prod-web-01:   $142.00 (Standard_D4s_v3, westus)
  3. vm-staging-app:   $98.00  (Standard_B4ms, centralus)
  4. storage-shared:   $185.00 (Azure Files Premium)
  5. vm-dev-cluster:   $75.00  (Standard_B2s, eastus)

⚠ Cost Increase: +12% vs. previous month
💡 Optimization Potential: $340/month (27% reduction)
```

### Set Budget Alerts

```bash
# Set monthly budget
azlin util cost set-budget 1500

# Set budget with alerts
azlin util cost set-budget 1500 \
  --alert-at 80 \
  --alert-at 90 \
  --alert-at 100

# Configure alert notifications
azlin util cost configure-alerts \
  --email admin@example.com \
  --slack https://hooks.slack.com/services/...
```

**Output**:
```
✓ Monthly budget set to $1,500
✓ Alert thresholds configured:
  - 80% ($1,200): Warning
  - 90% ($1,350): Critical
  - 100% ($1,500): Budget Exceeded

Notifications will be sent to:
  - admin@example.com
  - Slack: #azure-costs
```

### Get Cost Recommendations

```bash
# Generate cost optimization recommendations
azlin util cost recommendations

# Show high-impact recommendations only
azlin util cost recommendations --high-impact

# Include detailed analysis
azlin util cost recommendations --detailed
```

**Output**:
```
Cost Optimization Recommendations
===================================

High Impact (Est. Savings: $285/month):

1. Right-Size Overprovisioned VMs
   Impact: $185/month

   vm-prod-db-01 (Standard_D8s_v3, eastus)
   - Current: 8 vCPUs, 32GB RAM
   - Avg CPU: 18%, Avg Memory: 35%
   - Recommendation: Downgrade to Standard_D4s_v3
   - Savings: $142/month (50% reduction)

   vm-staging-app (Standard_B4ms, centralus)
   - Current: 4 vCPUs, 16GB RAM
   - Avg CPU: 12%, Avg Memory: 28%
   - Recommendation: Downgrade to Standard_B2ms
   - Savings: $43/month (44% reduction)

2. Auto-Stop Idle VMs
   Impact: $100/month

   vm-dev-test-02, vm-dev-test-03, vm-qa-temp
   - Running 24/7 but used < 20% of time
   - Recommendation: Auto-stop during off-hours (6 PM - 8 AM)
   - Savings: $100/month (67% reduction for these VMs)

Medium Impact (Est. Savings: $55/month):

3. Use Azure Hybrid Benefit
   Impact: $45/month

   5 Windows VMs without Hybrid Benefit
   - Recommendation: Enable Azure Hybrid Benefit
   - Requires: Valid Windows Server licenses

4. Optimize Storage Tiers
   Impact: $10/month

   - Move infrequently accessed data to Cool tier
   - Identified 500GB of data with < 1 access/month

Apply All Recommendations: azlin util cost apply-recommendations
```

## Cost Dashboard

### Real-Time Monitoring

```bash
# Interactive cost dashboard
azlin util cost dashboard

# Dashboard with auto-refresh
azlin util cost dashboard --refresh 5m
```

**Dashboard Output**:
```
┌─ Azure Cost Dashboard ─────────────────────────────────────────┐
│                                                                 │
│ Current Month: December 2025                                    │
│ Total Spending: $847.50 / $1,500.00 budget (56.5%)             │
│ Days Remaining: 18                                              │
│ Projected Total: $1,248.00 (within budget)                      │
│                                                                 │
│ ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░ 56.5%    │
│                                                                 │
│ Daily Breakdown (Last 7 days):                                  │
│ Mon  ████████████ $42.50                                        │
│ Tue  ████████████ $41.80                                        │
│ Wed  ████████████ $43.20                                        │
│ Thu  ████████████ $42.10                                        │
│ Fri  ████████████ $41.90                                        │
│ Sat  ██████       $28.00 (weekend auto-stop)                    │
│ Sun  ██████       $27.50 (weekend auto-stop)                    │
│                                                                 │
│ Top Cost Drivers:                                               │
│ 1. VMs:          $622.00 (73%)  ▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░           │
│ 2. Storage:      $165.00 (19%)  ▓▓▓▓░░░░░░░░░░░░░░░░           │
│ 3. Network:      $52.50  (6%)   ▓░░░░░░░░░░░░░░░░░░░           │
│ 4. Other:        $8.00   (1%)   ░░░░░░░░░░░░░░░░░░░░           │
│                                                                 │
│ 💡 Active Optimizations:                                        │
│ - Auto-stop enabled: 8 VMs (saving $120/month)                  │
│ - Right-sizing pending: 3 VMs (potential $185/month)            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

Press 'q' to quit, 'r' to refresh, 'd' for details
```

### Cost Breakdown Views

```bash
# By VM
azlin util cost --by-vm

# By region
azlin util cost --by-region

# By resource group
azlin util cost --by-resource-group

# By tags
azlin util cost --by-tag environment
azlin util cost --by-tag cost-center

# Compare time periods
azlin util cost --compare \
  --period1 "last-month" \
  --period2 "this-month"
```

## Budget Management

### Creating Budgets

```bash
# Set overall budget
azlin util cost set-budget 2000

# Set per-VM budget
azlin util cost set-budget --vm vm-prod-01 --amount 200

# Set per-region budget
azlin util cost set-budget --region eastus --amount 800

# Set project budget
azlin util cost set-budget --tag project=web-app --amount 500
```

### Budget Alerts

```bash
# Configure alert thresholds
azlin util cost configure-alerts \
  --threshold 75 --action notify \
  --threshold 90 --action notify+warn \
  --threshold 100 --action notify+warn+stop

# Alert actions:
# - notify: Send email/Slack notification
# - warn: Add warning to dashboard
# - stop: Stop least critical VMs
```

### Budget Tracking

```bash
# Show budget status
azlin util cost budget-status

# Show budget history
azlin util cost budget-history --last 6m

# Export budget report
azlin util cost budget-report --format pdf --output december-budget.pdf
```

## Cost Optimization Features

### 1. Idle VM Detection

Automatically identify and manage idle VMs:

```bash
# Detect idle VMs
azlin util cost detect-idle

# Configure idle thresholds
azlin util cost configure-idle \
  --cpu-threshold 5 \
  --duration 2h

# Auto-stop idle VMs
azlin util cost auto-stop-idle --enable

# Configure auto-stop schedule
azlin util cost auto-stop-idle \
  --schedule "weekdays:6PM-8AM" \
  --schedule "weekends:all"
```

**Output**:
```
Idle VM Detection Results:

Currently Idle (>2 hours, <5% CPU):
  - vm-dev-test-01: Idle for 8h 23m
  - vm-staging-02: Idle for 14h 45m
  - vm-qa-temp: Idle for 3 days

Auto-Stop Schedule:
  Weekdays: 6 PM - 8 AM (14 hours)
  Weekends: All day (48 hours)

Estimated Monthly Savings: $280
```

### 2. Right-Sizing Recommendations

```bash
# Analyze VM sizes
azlin util cost analyze-sizes

# Get right-sizing recommendations
azlin util cost recommend-sizes

# Apply recommended sizes
azlin util cost apply-size vm-prod-01 --recommended
```

**Analysis Output**:
```
VM Size Analysis:

vm-prod-db-01 (Standard_D8s_v3):
  Provisioned: 8 vCPUs, 32GB RAM
  Avg Usage: 1.5 vCPUs (18%), 11GB RAM (35%)
  Peak Usage: 3 vCPUs (38%), 18GB RAM (56%)

  Recommendation: Standard_D4s_v3
  Confidence: High (based on 30 days data)
  Cost Impact: $142/month savings (50% reduction)
  Risk: Low (peak usage well within new size)

  Apply: azlin util cost apply-size vm-prod-db-01 Standard_D4s_v3
```

### 3. Reserved Instances Analysis

```bash
# Analyze reservation opportunities
azlin util cost analyze-reservations

# Show RI recommendations
azlin util cost recommend-reservations

# Calculate RI savings
azlin util cost calculate-ri-savings --term 1yr --term 3yr
```

**Output**:
```
Reserved Instance Opportunities:

Standard_D4s_v3 (eastus):
  Current Usage: 3 VMs running continuously
  Current Monthly Cost: $426.00

  1-Year Reserved Instance:
  - Monthly Cost: $298.20 (30% discount)
  - Upfront: $0 (monthly payment)
  - Annual Savings: $1,533.60

  3-Year Reserved Instance:
  - Monthly Cost: $212.50 (50% discount)
  - Upfront: $0 (monthly payment)
  - 3-Year Savings: $7,686.00

Recommendation: Purchase 3x Standard_D4s_v3 RIs (3-year term)
```

### 4. Spot Instance Recommendations

```bash
# Analyze spot instance suitability
azlin util cost analyze-spot

# Show spot instance recommendations
azlin util cost recommend-spot

# Convert VM to spot
azlin new myvm --spot --eviction-policy Deallocate
```

**Output**:
```
Spot Instance Analysis:

Suitable for Spot Instances (5 VMs):
  - vm-batch-worker-*: Batch jobs, fault-tolerant
    Potential Savings: 80% ($320/month)

  - vm-dev-test-*: Development VMs, non-critical
    Potential Savings: 70% ($210/month)

Not Suitable (2 VMs):
  - vm-prod-db-01: Production database, requires high availability
  - vm-prod-web-01: Production web server, customer-facing

Total Potential Savings: $530/month
```

### 5. Storage Optimization

```bash
# Analyze storage costs
azlin util cost analyze-storage

# Optimize storage tiers
azlin util cost optimize-storage

# Move data to appropriate tiers
azlin util cost apply-storage-tier \
  --data-age 30d \
  --target-tier Cool
```

## Cost Forecasting

### Predictive Analytics

```bash
# Forecast next month's costs
azlin util cost forecast

# Forecast with scenario analysis
azlin util cost forecast \
  --scenario baseline \
  --scenario "add 5 VMs" \
  --scenario "enable auto-stop"

# Long-term forecast
azlin util cost forecast --period 6m
```

**Forecast Output**:
```
Cost Forecast (Next 30 days)

Based on Historical Usage (Last 90 days):
  Predicted Total: $1,285.00
  Confidence Range: $1,220 - $1,350 (95% confidence)
  Trend: +3% vs. previous month

Key Assumptions:
  - Current VM count remains stable (15 VMs)
  - No significant workload changes
  - Existing auto-stop schedules continue

Scenario Analysis:

Scenario 1: Baseline (current state)
  Predicted Cost: $1,285.00

Scenario 2: Add 5 new Standard_B2s VMs
  Predicted Cost: $1,485.00 (+$200)

Scenario 3: Enable auto-stop for dev VMs
  Predicted Cost: $1,065.00 (-$220)

Recommendation: Apply Scenario 3 to stay within $1,500 budget
```

### Trend Analysis

```bash
# Show cost trends
azlin util cost trends

# Analyze cost drivers
azlin util cost analyze-trends

# Compare periods
azlin util cost compare --months 3
```

## Automated Cost Actions

### Auto-Stop Rules

```bash
# Create auto-stop rule
azlin util cost create-rule \
  --name "stop-dev-vms-evening" \
  --selector "tag:environment=dev" \
  --action stop \
  --schedule "weekdays:6PM-8AM"

# Create budget-based rule
azlin util cost create-rule \
  --name "emergency-budget-stop" \
  --trigger "budget-exceeded:95%" \
  --action "stop-lowest-priority" \
  --exclude "tag:critical=true"

# List rules
azlin util cost list-rules

# Disable rule
azlin util cost disable-rule stop-dev-vms-evening
```

### Automatic Resizing

```bash
# Enable automatic right-sizing
azlin util cost enable-auto-resize \
  --vm vm-prod-01 \
  --review-period 7d \
  --confidence-threshold 90

# Configure resize windows
azlin util cost configure-resize \
  --maintenance-window "Sunday:2AM-4AM"
```

## Cost Tagging Strategy

### Tag-Based Cost Allocation

```bash
# Set cost allocation tags
azlin vm tag myvm \
  --cost-center engineering \
  --project web-app \
  --environment production

# View costs by tag
azlin util cost --by-tag cost-center
azlin util cost --by-tag project

# Generate chargeback report
azlin util cost chargeback \
  --tag cost-center \
  --format csv \
  --output chargeback-december.csv
```

**Chargeback Report**:
```
Cost Allocation Report - December 2025

By Cost Center:
  Engineering:    $685.00 (55%)
    - web-app:      $420.00
    - mobile-app:   $180.00
    - infrastructure: $85.00

  Marketing:      $285.00 (23%)
    - analytics:    $185.00
    - campaigns:    $100.00

  Sales:          $122.50 (10%)
  Operations:     $155.00 (12%)

Total: $1,247.50
```

## Integration & Automation

### Cost API

```python
from azlin.modules.cost_estimator import CostEstimator

# Get cost summary
estimator = CostEstimator()
summary = estimator.get_cost_summary(period="30d")
print(f"Total: ${summary.total}")
print(f"Projected Monthly: ${summary.projected_monthly}")

# Get recommendations
recommendations = estimator.get_recommendations()
for rec in recommendations:
    print(f"{rec.title}: ${rec.estimated_savings}/month")

# Set budget alert
estimator.set_budget(amount=1500, thresholds=[80, 90, 100])

# Get forecast
forecast = estimator.forecast(days=30)
print(f"Forecasted Cost: ${forecast.predicted_amount}")
```

### Webhooks

```bash
# Configure webhook for budget alerts
azlin util cost webhook add \
  --url https://your-api.com/cost-alert \
  --event budget-threshold \
  --event budget-exceeded

# Webhook payload example:
{
  "event": "budget-threshold",
  "threshold": 90,
  "current_spend": 1350.00,
  "budget": 1500.00,
  "period": "2025-12",
  "timestamp": "2025-12-20T14:30:00Z"
}
```

## Best Practices

1. **Set Realistic Budgets**
   - Base budgets on historical data
   - Include 10-15% buffer for unexpected costs
   - Review and adjust quarterly

2. **Use Granular Tagging**
   - Tag all resources consistently
   - Include cost-center, project, environment tags
   - Automate tagging in VM creation

3. **Monitor Daily**
   - Check dashboard regularly
   - Set up alert notifications
   - Review weekly cost trends

4. **Act on Recommendations**
   - Review recommendations weekly
   - Test optimizations in dev first
   - Track savings from applied recommendations

5. **Leverage Automation**
   - Enable auto-stop for non-production VMs
   - Use auto-resize for appropriate workloads
   - Configure budget-based actions

6. **Plan for Reserved Instances**
   - Analyze stable workloads for RI opportunities
   - Start with 1-year terms
   - Consider 3-year for predictable loads

## See Also

- [Monitoring](./index.md)
- [VM Management](../vm-lifecycle/index.md)
- [Batch Operations](../batch/index.md)
- [Cost Command Reference](../commands/util/cost.md)

---

*Documentation last updated: 2025-12-03*
