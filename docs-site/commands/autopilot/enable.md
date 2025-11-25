# azlin autopilot enable

Enable autopilot with specified budget and strategy.

## Synopsis

```bash
azlin autopilot enable --budget <amount> [OPTIONS]
```

## Description

Enables autopilot to automatically manage VM lifecycle and stay within the specified monthly budget. When enabled, autopilot will:

1. Create autopilot configuration
2. Analyze existing VM usage patterns
3. Start monitoring costs against budget
4. Send notifications before taking actions
5. Automatically optimize VMs based on strategy

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `-b, --budget INTEGER` | Monthly budget in USD (required) | - |
| `-s, --strategy` | Cost optimization strategy: `conservative`, `balanced`, `aggressive` | `balanced` |
| `--idle-threshold INTEGER` | Minutes before VM considered idle | `120` |
| `--cpu-threshold INTEGER` | CPU utilization threshold for downsizing (percent) | `20` |
| `-h, --help` | Show help message | - |

## Examples

### Enable with default settings

```bash
azlin autopilot enable --budget 500
```

This enables autopilot with:
- $500/month budget
- Balanced strategy
- 2-hour idle threshold
- 20% CPU threshold

### Enable with aggressive strategy

```bash
azlin autopilot enable --budget 1000 --strategy aggressive
```

Aggressive strategy provides maximum cost savings by:
- Stopping VMs idle for 30+ minutes
- Aggressively downsizing low-utilization VMs
- More frequent optimization checks

### Enable with conservative settings

```bash
azlin autopilot enable --budget 500 --strategy conservative --idle-threshold 240
```

Conservative settings:
- Only stops VMs idle for 4+ hours
- Never downsizes running VMs
- Safer for production environments

### Custom thresholds

```bash
azlin autopilot enable --budget 750 \
  --strategy balanced \
  --idle-threshold 90 \
  --cpu-threshold 15
```

Custom configuration:
- $750 monthly budget
- Stop VMs idle for 90+ minutes
- Downsize VMs with <15% CPU utilization

## What Happens When Enabled

1. **Configuration Creation**: Creates `~/.azlin/autopilot.toml` with settings
2. **Initial Analysis**: Scans existing VMs and usage patterns
3. **Cost Baseline**: Calculates current monthly spend projection
4. **Monitoring Start**: Begins tracking VM activity and costs
5. **Notification Setup**: Prepares to send alerts before actions

## Output Example

```
Autopilot Enabled

Budget:            $500/month
Strategy:          balanced
Idle Threshold:    120 minutes
CPU Threshold:     20%

Current VMs:       8 VMs found
Current Spend:     $245/month (projected)
Remaining Budget:  $255/month

Autopilot will:
  - Monitor VM activity 24/7
  - Stop VMs idle for 120+ minutes
  - Downsize VMs with <20% CPU utilization
  - Send notifications before taking actions

Run 'azlin autopilot status' to view status.
```

## Strategy Comparison

| Strategy | Idle Time | CPU Threshold | Downsize | Best For |
|----------|-----------|---------------|----------|----------|
| Conservative | 2+ hours | Never | No | Production, safety first |
| Balanced | 1+ hours | <20% CPU | Yes | Most users, good balance |
| Aggressive | 30+ min | <30% CPU | Yes | Maximum savings, dev/test |

## Budget Enforcement

Autopilot enforces budgets by:

1. **Monitoring**: Tracks actual Azure costs
2. **Projection**: Calculates monthly spend projection
3. **Alerts**: Warns when approaching budget (80%, 90%, 95%)
4. **Action**: Stops lowest-priority VMs when budget reached
5. **Protection**: Never stops VMs with named sessions

## Notifications

Autopilot sends notifications via:
- Console output when commands run
- Log files in `~/.azlin/logs/autopilot.log`
- Optional email/webhook integration (config)

## Configuration File

After enabling, configuration is stored in `~/.azlin/autopilot.toml`:

```toml
[autopilot]
enabled = true
budget_monthly = 500
strategy = "balanced"
idle_threshold = 120
cpu_threshold = 20

[autopilot.work_hours]
# Learned over time
monday = ["09:00-17:00"]
tuesday = ["09:00-17:00"]
# ...

[autopilot.exclusions]
# VMs to never touch
protected_vms = []
protected_tags = ["production", "critical"]
```

## Common Workflows

### Start with dry-run

```bash
# Enable autopilot
azlin autopilot enable --budget 500

# Check what it would do
azlin autopilot run --dry-run

# View status
azlin autopilot status
```

### Production setup

```bash
# Enable with conservative settings
azlin autopilot enable --budget 2000 --strategy conservative

# Protect production VMs
azlin tag prod-vm-1 --add critical=true
azlin tag prod-vm-2 --add critical=true
```

### Development environment

```bash
# Enable with aggressive settings for maximum savings
azlin autopilot enable --budget 300 --strategy aggressive

# Run immediately to clean up
azlin autopilot run
```

## Troubleshooting

### Autopilot already enabled

```
Error: Autopilot is already enabled
```

**Solution**: Disable first, then re-enable:
```bash
azlin autopilot disable
azlin autopilot enable --budget 500
```

### Budget too low

```
Warning: Budget $100/month is below current spend $245/month
```

**Solution**: Either increase budget or stop VMs manually:
```bash
# Increase budget
azlin autopilot enable --budget 300

# Or stop VMs first
azlin stop vm-1 vm-2
azlin autopilot enable --budget 100
```

### No VMs found

```
Warning: No VMs found in resource group
```

**Solution**: This is normal for new resource groups. Autopilot will monitor as you create VMs.

## Related Commands

- [azlin autopilot disable](disable.md) - Disable autopilot
- [azlin autopilot status](status.md) - Check autopilot status
- [azlin autopilot config](config.md) - Modify configuration
- [azlin cost](../util/cost.md) - View cost estimates
