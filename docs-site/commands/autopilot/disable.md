# azlin autopilot disable

Disable autopilot and stop automated VM management.

## Synopsis

```bash
azlin autopilot disable [OPTIONS]
```

## Description

Disables autopilot and stops all automated actions. Optionally keeps configuration for future use.

When disabled, autopilot will:
- Stop monitoring VM activity
- Stop automated cost optimization
- Stop sending notifications
- Optionally preserve configuration settings

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--keep-config` | Keep configuration file (just disable autopilot) | `false` |
| `-h, --help` | Show help message | - |

## Examples

### Disable completely

```bash
azlin autopilot disable
```

This removes autopilot configuration entirely.

### Disable but keep configuration

```bash
azlin autopilot disable --keep-config
```

This disables autopilot but preserves settings in `~/.azlin/autopilot.toml` for easy re-enable.

## What Happens When Disabled

1. **Monitoring Stops**: No more VM activity tracking
2. **Actions Stop**: No automated stops or downsizing
3. **Notifications Stop**: No more alerts
4. **Configuration**: Optionally removed or marked disabled

## Output Example

### Complete disable

```
Autopilot Disabled

Previous Budget:   $500/month
Previous Strategy: balanced
Total Savings:     $145 this month

Configuration removed from ~/.azlin/autopilot.toml

VMs are no longer automatically managed.
Run 'azlin autopilot enable' to re-enable.
```

### Disable with keep-config

```
Autopilot Disabled (configuration preserved)

Previous Budget:   $500/month
Previous Strategy: balanced
Total Savings:     $145 this month

Configuration preserved in ~/.azlin/autopilot.toml
VMs are no longer automatically managed.

Run 'azlin autopilot enable' to re-enable with saved settings.
```

## Configuration File Behavior

### Without --keep-config (default)

The configuration file `~/.azlin/autopilot.toml` is deleted entirely.

### With --keep-config

The configuration file is updated to mark autopilot as disabled:

```toml
[autopilot]
enabled = false
budget_monthly = 500
strategy = "balanced"
idle_threshold = 120
cpu_threshold = 20

# All other settings preserved
```

## Re-enabling After Disable

### After complete disable

```bash
# Must specify all settings again
azlin autopilot enable --budget 500 --strategy balanced
```

### After disable with --keep-config

```bash
# Re-enables with preserved settings
azlin autopilot enable --budget 500
```

The preserved configuration provides defaults, but you can override them.

## Common Workflows

### Temporarily disable

```bash
# Disable but keep configuration
azlin autopilot disable --keep-config

# Later, re-enable easily
azlin autopilot enable --budget 500
```

### Disable during maintenance

```bash
# Disable before major changes
azlin autopilot disable --keep-config

# Perform maintenance
azlin new --name maintenance-vm
# ... work ...

# Re-enable after maintenance
azlin autopilot enable --budget 500
```

### Complete removal

```bash
# Remove all autopilot configuration
azlin autopilot disable

# Verify removal
ls ~/.azlin/autopilot.toml
# File not found
```

## Viewing Savings Before Disable

```bash
# Check total savings
azlin autopilot status

# Then disable
azlin autopilot disable
```

Example status output:
```
Autopilot Status

Enabled:           Yes
Budget:            $500/month
Current Spend:     $245/month
Savings This Month: $145

Actions This Month:
  - Stopped 12 idle VMs
  - Downsized 3 underutilized VMs
  - Prevented budget overrun: Yes
```

## Troubleshooting

### Autopilot not enabled

```
Error: Autopilot is not currently enabled
```

**Solution**: Nothing to do, autopilot is already disabled.

### Configuration file not found

```
Warning: Configuration file not found at ~/.azlin/autopilot.toml
```

**Solution**: Autopilot was never enabled or already completely removed.

### VMs still running

Disabling autopilot does not stop currently running VMs. It only stops future automated actions.

```bash
# Disable autopilot
azlin autopilot disable

# VMs remain in current state
azlin list
# vm-1: Running
# vm-2: Running
# vm-3: Stopped (by autopilot earlier)
```

## Related Commands

- [azlin autopilot enable](enable.md) - Enable autopilot
- [azlin autopilot status](status.md) - View autopilot status
- [azlin autopilot config](config.md) - Configure settings
