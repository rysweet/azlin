# Autopilot Commands

AI-powered cost optimization and VM lifecycle management.

Autopilot learns your VM usage patterns and automatically manages VM lifecycle to stay within budget.

## Overview

Autopilot continuously monitors your VM fleet and makes intelligent decisions to:

- Automatically stop idle VMs
- Downsize underutilized VMs
- Enforce budget constraints
- Learn your work hours and usage patterns
- Send notifications before taking actions

## Features

- **Pattern Learning**: Observes your usage patterns to avoid stopping VMs during active hours
- **Cost Optimization**: Automatically manages VM lifecycle to stay within budget
- **Transparency**: Always notifies before taking actions
- **Configurable Strategies**: Choose between conservative, balanced, or aggressive optimization

## Commands

- [enable](enable.md) - Enable autopilot with budget and strategy
- [disable](disable.md) - Disable autopilot
- [status](status.md) - Show autopilot status and budget information
- [config](config.md) - Configure autopilot settings
- [run](run.md) - Manually run autopilot to check and execute actions

## Quick Start

```bash
# Enable autopilot with $500/month budget
azlin autopilot enable --budget 500 --strategy balanced

# Check status
azlin autopilot status

# Run manually to see recommendations
azlin autopilot run --dry-run
```

## Optimization Strategies

### Conservative
- Only stops clearly idle VMs (2+ hours no activity)
- Never downsizes running VMs
- Maximum safety, slower cost reduction

### Balanced (Recommended)
- Stops VMs idle for 1+ hours
- Downsizes VMs with low utilization
- Good balance of cost savings and convenience

### Aggressive
- Stops VMs idle for 30+ minutes
- Aggressively downsizes underutilized VMs
- Maximum cost savings, may interrupt work

## How It Works

1. **Monitoring**: Autopilot tracks CPU utilization, network activity, and login patterns
2. **Analysis**: Identifies idle VMs and usage patterns
3. **Notification**: Sends alert before taking action (configurable warning time)
4. **Action**: Stops or downsizes VMs based on strategy
5. **Learning**: Adapts to your work schedule over time

## Configuration

Autopilot stores configuration in `~/.azlin/autopilot.toml`:

```toml
[autopilot]
enabled = true
budget_monthly = 500
strategy = "balanced"
idle_threshold = 120  # minutes
cpu_threshold = 20    # percent
```

## Safety Features

- **Dry-run mode**: Preview actions before executing
- **Named session protection**: Never stops VMs with named sessions (unless configured)
- **Work hours learning**: Learns your active hours to avoid disruption
- **Notification system**: Alerts before taking actions
- **Manual override**: Run manually with `azlin autopilot run`

## Related Commands

- [azlin status](../vm/status.md) - View VM status
- [azlin cost](../util/cost.md) - View cost estimates
- [azlin prune](../util/prune.md) - Manually prune inactive VMs
