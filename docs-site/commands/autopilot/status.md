# azlin autopilot status

Show autopilot status and budget information.

## Synopsis

```bash
azlin autopilot status
```

## Description

Displays comprehensive autopilot status including:
- Current configuration
- Budget status and spending
- Recent actions taken
- Recommendations for optimization
- Projected savings

## Options

| Option | Description |
|--------|-------------|
| `-h, --help` | Show help message |

## Output

### When Enabled

```
Autopilot Status

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Configuration
-------------
Enabled:           Yes
Budget:            $500/month
Strategy:          balanced
Idle Threshold:    120 minutes
CPU Threshold:     20%

Budget Status
-------------
Current Spend:     $245/month (projected)
Remaining Budget:  $255/month (51%)
Savings This Month: $145
Budget Alert:      Normal

Recent Actions (Last 7 Days)
----------------------------
2025-11-24 10:30   Stopped vm-test-123 (idle 150 min)
2025-11-24 09:15   Stopped vm-dev-456 (idle 180 min)
2025-11-23 16:45   Downsized vm-staging-789 (CPU <15%)
2025-11-23 14:20   Stopped vm-temp-001 (idle 200 min)

Active VMs
----------
vm-prod-1          Running   High utilization   Protected
vm-dev-main        Running   Normal activity    Active
vm-staging-2       Running   Low utilization    Consider downsizing

Recommendations
---------------
✓ Budget is healthy (51% remaining)
→ Consider stopping vm-staging-2 (idle 90 min)
→ 2 VMs can be downsized to save $45/month

Work Hours Pattern (Learned)
-----------------------------
Monday:            09:00 - 18:00
Tuesday:           09:00 - 18:00
Wednesday:         09:00 - 18:00
Thursday:          09:00 - 17:30
Friday:            09:00 - 16:00
Weekend:           Inactive

Run 'azlin autopilot run --dry-run' to preview actions.
```

### When Disabled

```
Autopilot Status

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Enabled:           No

Autopilot is currently disabled.

Run 'azlin autopilot enable --budget <amount>' to enable.
```

### Budget Warning State

```
Autopilot Status

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Configuration
-------------
Enabled:           Yes
Budget:            $500/month
Strategy:          balanced

Budget Status
-------------
Current Spend:     $475/month (projected)
Remaining Budget:  $25/month (5%)
Savings This Month: $80
Budget Alert:      ⚠ WARNING - Approaching budget limit

Recent Actions (Last 7 Days)
----------------------------
2025-11-24 10:30   Stopped vm-test-123 (budget protection)
2025-11-24 09:15   Stopped vm-dev-456 (budget protection)
2025-11-23 16:45   Stopped vm-temp-001 (budget protection)

Recommendations
---------------
⚠ Budget is critical (95% used)
→ Consider stopping additional VMs
→ Or increase budget with 'azlin autopilot enable --budget 700'
→ 3 VMs running with low utilization
```

## Status Components

### Configuration

Shows current autopilot settings:
- **Enabled**: Whether autopilot is active
- **Budget**: Monthly budget limit
- **Strategy**: Optimization strategy (conservative/balanced/aggressive)
- **Thresholds**: Idle time and CPU utilization thresholds

### Budget Status

Tracks spending and budget:
- **Current Spend**: Projected monthly cost based on current usage
- **Remaining Budget**: How much budget is left
- **Savings**: How much autopilot has saved this month
- **Budget Alert**: Normal, Warning, or Critical status

### Recent Actions

Lists recent autopilot actions:
- Timestamp of action
- Action taken (stopped, downsized, etc.)
- Reason for action
- VM affected

### Active VMs

Shows current VM state:
- VM name
- Current status (running/stopped)
- Activity level
- Protection status or recommendations

### Recommendations

Actionable suggestions:
- VMs that should be stopped
- VMs that can be downsized
- Budget adjustments needed
- Optimization opportunities

### Work Hours Pattern

Shows learned usage patterns:
- Active hours by day of week
- Helps predict when VMs are needed
- Improves optimization accuracy

## Examples

### Check status regularly

```bash
# Quick status check
azlin autopilot status
```

### Monitor budget usage

```bash
# Check status and budget
azlin autopilot status | grep -A 5 "Budget Status"
```

### View recent actions

```bash
# See what autopilot has done
azlin autopilot status | grep -A 10 "Recent Actions"
```

### Check recommendations

```bash
# View optimization suggestions
azlin autopilot status | grep -A 5 "Recommendations"
```

## Budget Alert Levels

| Alert Level | Budget Used | Description |
|-------------|-------------|-------------|
| Normal | 0-79% | Healthy budget status |
| Warning | 80-94% | Approaching limit, autopilot increases activity |
| Critical | 95-100% | At limit, autopilot stops lowest-priority VMs |

## Common Workflows

### Daily monitoring

```bash
# Morning check
azlin autopilot status

# Review recommendations
azlin autopilot run --dry-run

# Execute if needed
azlin autopilot run
```

### Budget management

```bash
# Check current spend
azlin autopilot status

# If approaching limit, review VMs
azlin list --all

# Stop unnecessary VMs
azlin stop vm-test-*

# Or increase budget
azlin autopilot enable --budget 700
```

### Performance tuning

```bash
# Check work hours pattern
azlin autopilot status

# If pattern is inaccurate, adjust settings
azlin autopilot config --set idle_threshold=180

# Verify changes
azlin autopilot status
```

## Understanding Savings

Savings are calculated as:
```
Savings = (Cost without autopilot) - (Actual cost)
```

Includes:
- VMs stopped during idle periods
- VMs downsized to appropriate sizes
- Resources deallocated when not needed

Example:
```
8 VMs running 24/7:        $480/month
With autopilot (smart stops): $335/month
Savings:                   $145/month (30%)
```

## Troubleshooting

### Status shows no recent actions

```
Recent Actions (Last 7 Days)
----------------------------
No actions taken
```

**Possible reasons:**
- All VMs are actively used
- Budget has plenty of headroom
- Thresholds are too conservative

**Solutions:**
```bash
# Check VM utilization
azlin status

# Adjust thresholds if needed
azlin autopilot config --set idle_threshold=90

# Run manually
azlin autopilot run --dry-run
```

### Budget always showing critical

```
Budget Alert: ⚠ CRITICAL - Over budget
```

**Solutions:**
```bash
# Increase budget
azlin autopilot enable --budget 700

# Or use aggressive strategy
azlin autopilot enable --budget 500 --strategy aggressive

# Or manually stop VMs
azlin stop $(azlin list --stopped=false | tail -n +2 | awk '{print $1}')
```

### Work hours pattern inaccurate

**Solutions:**
- Pattern improves over 2-4 weeks of usage
- Manually edit `~/.azlin/autopilot.toml` if needed
- Use more aggressive idle threshold to override pattern

## Related Commands

- [azlin autopilot enable](enable.md) - Enable autopilot
- [azlin autopilot disable](disable.md) - Disable autopilot
- [azlin autopilot run](run.md) - Run autopilot manually
- [azlin cost](../util/cost.md) - View detailed cost breakdown
