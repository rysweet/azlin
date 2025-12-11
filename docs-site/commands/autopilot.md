# azlin autopilot

AI-powered cost optimization and VM lifecycle management.

Autopilot learns your VM usage patterns and automatically manages
VM lifecycle to stay within budget.

Features:
- Learns work hours and idle patterns
- Auto-stops idle VMs
- Downsizes underutilized VMs
- Enforces budget constraints
- Transparent notifications

Example:
    azlin autopilot enable --budget 500 --strategy balanced


## Description

AI-powered cost optimization and VM lifecycle management.
Autopilot learns your VM usage patterns and automatically manages
VM lifecycle to stay within budget.
Features:
- Learns work hours and idle patterns
- Auto-stops idle VMs
- Downsizes underutilized VMs
- Enforces budget constraints
- Transparent notifications

## Usage

```bash
azlin autopilot
```

## Subcommands

### config

Configure autopilot settings.

Example:
    azlin autopilot config --set budget_monthly=1000
    azlin autopilot config --set strategy=aggressive
    azlin autopilot config --show


**Usage:**
```bash
azlin autopilot config [OPTIONS]
```

**Options:**
- `--set` - Set configuration value (key=value)
- `--show` - Show full configuration

### disable

Disable autopilot.

This will stop all automated actions but optionally keep
configuration for future use.

Example:
    azlin autopilot disable
    azlin autopilot disable --keep-config


**Usage:**
```bash
azlin autopilot disable [OPTIONS]
```

**Options:**
- `--keep-config` - Keep configuration file (just disable autopilot)

### enable

Enable autopilot with specified budget and strategy.

This will:
1. Create autopilot configuration
2. Analyze existing VM usage patterns
3. Start monitoring costs against budget
4. Send notifications before taking actions

Example:
    azlin autopilot enable --budget 500 --strategy balanced


**Usage:**
```bash
azlin autopilot enable [OPTIONS]
```

**Options:**
- `--budget`, `-b` - Monthly budget in USD
- `--strategy`, `-s` - Cost optimization strategy
- `--idle-threshold` - Minutes before VM considered idle (default: 120)
- `--cpu-threshold` - CPU utilization threshold for downsizing (default: 20%%)

### run

Run autopilot manually to check and execute actions.

By default, shows recommendations without executing.
Use without --dry-run to execute actions.

Example:
    azlin autopilot run --dry-run
    azlin autopilot run


**Usage:**
```bash
azlin autopilot run [OPTIONS]
```

**Options:**
- `--dry-run` - Show what would be done without executing

### status

Show autopilot status and budget information.

Displays:
- Current configuration
- Budget status
- Recent actions
- Recommendations

Example:
    azlin autopilot status
