# azlin autopilot config

Configure autopilot settings after enabling.

## Synopsis

```bash
azlin autopilot config [OPTIONS]
```

## Description

Modify autopilot configuration without disabling and re-enabling. Allows fine-tuning of:
- Budget amounts
- Optimization strategy
- Idle and CPU thresholds
- Protected VMs and tags
- Notification settings

## Options

| Option | Description |
|--------|-------------|
| `--set TEXT` | Set configuration value (key=value format) |
| `--show` | Display full configuration |
| `-h, --help` | Show help message |

## Configuration Keys

### Budget Settings

| Key | Description | Example |
|-----|-------------|---------|
| `budget_monthly` | Monthly budget in USD | `--set budget_monthly=1000` |
| `budget_alert_threshold` | Alert when budget reaches % | `--set budget_alert_threshold=80` |

### Strategy Settings

| Key | Description | Values |
|-----|-------------|--------|
| `strategy` | Optimization strategy | `conservative`, `balanced`, `aggressive` |

### Threshold Settings

| Key | Description | Example |
|-----|-------------|---------|
| `idle_threshold` | Minutes before VM considered idle | `--set idle_threshold=180` |
| `cpu_threshold` | CPU % threshold for downsizing | `--set cpu_threshold=15` |

### Protection Settings

| Key | Description | Example |
|-----|-------------|---------|
| `protected_vms` | Comma-separated VM names | `--set protected_vms=vm1,vm2` |
| `protected_tags` | Comma-separated tag keys | `--set protected_tags=production,critical` |

### Notification Settings

| Key | Description | Example |
|-----|-------------|---------|
| `notify_before_action` | Notify before taking action | `--set notify_before_action=true` |
| `notification_delay` | Minutes to wait after notification | `--set notification_delay=15` |

## Examples

### View current configuration

```bash
azlin autopilot config --show
```

Output:
```toml
[autopilot]
enabled = true
budget_monthly = 500
strategy = "balanced"
idle_threshold = 120
cpu_threshold = 20
budget_alert_threshold = 80

[autopilot.protection]
protected_vms = []
protected_tags = ["production", "critical"]

[autopilot.notifications]
notify_before_action = true
notification_delay = 15

[autopilot.work_hours]
monday = ["09:00-18:00"]
tuesday = ["09:00-18:00"]
wednesday = ["09:00-18:00"]
thursday = ["09:00-17:30"]
friday = ["09:00-16:00"]
saturday = []
sunday = []
```

### Increase budget

```bash
azlin autopilot config --set budget_monthly=1000
```

### Change strategy

```bash
azlin autopilot config --set strategy=aggressive
```

### Adjust idle threshold

```bash
azlin autopilot config --set idle_threshold=180
```

This increases idle threshold to 3 hours.

### Adjust CPU threshold

```bash
azlin autopilot config --set cpu_threshold=15
```

This makes autopilot more aggressive about downsizing (downsize VMs with <15% CPU).

### Protect specific VMs

```bash
azlin autopilot config --set protected_vms=prod-vm-1,prod-vm-2
```

### Add protected tags

```bash
azlin autopilot config --set protected_tags=production,critical,database
```

### Multiple changes

```bash
azlin autopilot config --set budget_monthly=750
azlin autopilot config --set strategy=balanced
azlin autopilot config --set idle_threshold=90
```

Or in a script:
```bash
for setting in \
  "budget_monthly=750" \
  "strategy=balanced" \
  "idle_threshold=90"; do
  azlin autopilot config --set "$setting"
done
```

## Configuration File Location

Autopilot configuration is stored in:
```
~/.azlin/autopilot.toml
```

You can also manually edit this file, then verify with:
```bash
azlin autopilot config --show
```

## Configuration Validation

Autopilot validates configuration when set:

```bash
# Invalid strategy
azlin autopilot config --set strategy=turbo
# Error: Invalid strategy. Must be: conservative, balanced, or aggressive

# Invalid threshold
azlin autopilot config --set idle_threshold=-10
# Error: Idle threshold must be positive

# Budget too low
azlin autopilot config --set budget_monthly=10
# Warning: Budget is very low. Current projected spend: $245/month
```

## Common Workflows

### Increase budget during busy period

```bash
# Check current status
azlin autopilot status

# Increase budget
azlin autopilot config --set budget_monthly=1000

# Verify
azlin autopilot status
```

### Make optimization more aggressive

```bash
# Reduce idle threshold
azlin autopilot config --set idle_threshold=60

# Increase CPU threshold
azlin autopilot config --set cpu_threshold=25

# Change strategy
azlin autopilot config --set strategy=aggressive

# Test with dry-run
azlin autopilot run --dry-run
```

### Protect production VMs

```bash
# Add production tag to VMs
azlin tag prod-vm-1 --add environment=production
azlin tag prod-vm-2 --add environment=production

# Protect VMs with production tag
azlin autopilot config --set protected_tags=production

# Verify
azlin autopilot config --show
```

### Disable notifications

```bash
azlin autopilot config --set notify_before_action=false
```

Note: Use with caution. Notifications help prevent unexpected VM stops.

### Seasonal adjustment

```bash
# During low-activity period (holidays)
azlin autopilot config --set strategy=aggressive
azlin autopilot config --set idle_threshold=30

# During high-activity period
azlin autopilot config --set strategy=conservative
azlin autopilot config --set idle_threshold=240
```

## Advanced Configuration

### Manual work hours configuration

Edit `~/.azlin/autopilot.toml`:

```toml
[autopilot.work_hours]
monday = ["09:00-12:00", "13:00-18:00"]
tuesday = ["09:00-12:00", "13:00-18:00"]
wednesday = ["09:00-12:00", "13:00-18:00"]
thursday = ["09:00-12:00", "13:00-18:00"]
friday = ["09:00-12:00", "13:00-16:00"]
saturday = []
sunday = []
```

This sets:
- Lunch break 12:00-13:00 Monday-Thursday
- Half day Friday (end at 16:00)
- No weekend work

### Custom notification settings

Edit `~/.azlin/autopilot.toml`:

```toml
[autopilot.notifications]
notify_before_action = true
notification_delay = 30  # 30 minutes warning
notification_email = "team@example.com"
notification_webhook = "https://hooks.slack.com/services/..."
```

### Per-VM overrides

Edit `~/.azlin/autopilot.toml`:

```toml
[autopilot.vm_overrides]
"vm-special" = { idle_threshold = 300, never_downsize = true }
"vm-test" = { idle_threshold = 15, aggressive = true }
```

## Troubleshooting

### Configuration changes not taking effect

```bash
# Verify configuration was saved
azlin autopilot config --show

# Check autopilot is enabled
azlin autopilot status

# Run manually to test
azlin autopilot run --dry-run
```

### Cannot set configuration (autopilot disabled)

```
Error: Autopilot is not enabled
```

**Solution**: Enable autopilot first:
```bash
azlin autopilot enable --budget 500
azlin autopilot config --set idle_threshold=90
```

### Invalid configuration value

```
Error: Invalid value for 'strategy'
```

**Solution**: Check allowed values:
```bash
# View help
azlin autopilot config --help

# Or check documentation
azlin autopilot config --show
```

### Configuration file corrupted

```bash
# Backup current config
cp ~/.azlin/autopilot.toml ~/.azlin/autopilot.toml.backup

# Re-enable with fresh config
azlin autopilot disable
azlin autopilot enable --budget 500

# Manually migrate important settings from backup
```

## Related Commands

- [azlin autopilot enable](enable.md) - Enable autopilot with initial settings
- [azlin autopilot status](status.md) - View current configuration and status
- [azlin autopilot run](run.md) - Test configuration with dry-run
